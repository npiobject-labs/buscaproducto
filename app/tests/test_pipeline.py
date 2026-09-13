"""Búsqueda de principio a fin con dos adaptadores falsos: agrupación, puntuación, facetas e histórico."""

import asyncio

import pytest

from app.dominio import OfertaCruda
from app.fuentes import AdaptadorBase, registro


class _Falso(AdaptadorBase):
    nivel = "A"

    def __init__(self, slug, ofertas):
        self.slug, self._ofertas, self.llamadas = slug, ofertas, 0

    async def buscar(self, consulta, ctx):
        self.llamadas += 1
        return [OfertaCruda(**o) for o in self._ofertas]


A = [
    {
        "url": "https://a.example/beelink-s12",
        "titulo": "Beelink Mini S12 Pro Mini PC Intel N100 16GB DDR4 500GB SSD",
        "precio": 189.0,
        "envio": 0.0,
        "valoracion": 4.5,
    },
    {
        "url": "https://a.example/gmktec-g3",
        "titulo": "GMKtec NucBox G3 Plus N150 16GB+1TB fanless 12W",
        "precio": 229.0,
        "envio": 4.99,
    },
    {
        "url": "https://a.example/caro",
        "titulo": "Minisforum UM790 Pro Ryzen 9 7940HS 32GB 1TB",
        "precio": 649.0,
    },
    {"url": "https://a.example/poca-ram", "titulo": "Mini PC Celeron J4125 4GB 128GB", "precio": 119.0},
]
B = [
    {
        "url": "https://b.example/p/1",
        "titulo": "Beelink Mini S12 Pro (Intel N100, 16 GB RAM, 500 GB SSD) Windows 11",
        "precio": 179.0,
        "envio": 5.0,
        "ean": None,
    },
    {
        "url": "https://b.example/p/2",
        "titulo": "Lenovo ThinkCentre M720q Tiny i5-8400T 16GB 256GB SSD reacondicionado",
        "precio": 159.0,
        "estado_producto": "Reacondicionado",
    },
]

PETICION = {
    "texto": "mini pc",
    "especificaciones": [
        {"clave": "ram_gb", "operador": ">=", "valor": 8},
        {"clave": "almacenamiento_gb", "operador": ">=", "valor": 500},
        {"clave": "apto_24_7", "operador": "=", "valor": True},
    ],
    "precio_min": 130,
    "precio_max": 330,
    "interpretar": False,
    "fuentes": ["tienda-a", "tienda-b"],
    "usar_cache": False,
}


@pytest.fixture
async def con_falsos(cliente, monkeypatch):
    reg = registro()
    a, b = _Falso("tienda-a", A), _Falso("tienda-b", B)
    monkeypatch.setitem(reg, "tienda-a", a)
    monkeypatch.setitem(reg, "tienda-b", b)
    for nombre in ("Tienda A", "Tienda B"):
        r = await cliente.post(
            "/api/v1/herramientas",
            json={
                "nombre": nombre,
                "url": "https://x.example",
                "url_plantilla_busqueda": "https://x.example/?q={q}",
            },
        )
        assert r.status_code == 201
    return cliente, a, b


async def _terminar(cliente, bid):
    for _ in range(100):
        d = (await cliente.get(f"/api/v1/busquedas/{bid}")).json()
        if d["estado"] in ("terminada", "error"):
            return d
        await asyncio.sleep(0.05)
    raise AssertionError("no terminó")


async def test_pipeline_completo(con_falsos):
    cliente, a, b = con_falsos
    bid = (await cliente.post("/api/v1/busquedas", json=PETICION)).json()["id"]
    d = await _terminar(cliente, bid)
    assert d["estado"] == "terminada", d
    assert {f["slug"]: f["estado"] for f in d["fuentes"]} == {"tienda-a": "ok", "tienda-b": "ok"}
    assert d["facetas"]["total"] == 6 and d["facetas"]["fuentes"] == {"tienda-a": 4, "tienda-b": 2}
    r = (await cliente.get(f"/api/v1/busquedas/{bid}/resultados")).json()
    # rango 130-330 deja fuera el de 649 y el de 119; quedan 4 ofertas en 3 productos (los dos Beelink se agrupan)
    assert r["ofertas_filtradas"] == 4 and r["total_productos"] == 3, r
    beelink = next(p for p in r["productos"] if "Beelink" in p["nombre"])
    assert (
        beelink["n_tiendas"] == 2
        and beelink["mejor_precio"] == 184.0
        and beelink["ofertas"][0]["fuente"] == "tienda-b"
    )
    assert beelink["atributos"]["ram_gb"] == 16 and beelink["atributos"]["almacenamiento_gb"] == 500
    gmk = next(p for p in r["productos"] if "GMKtec" in p["nombre"])
    assert gmk["puntuacion"] == 100.0 and gmk["atributos"]["apto_24_7"] is True
    assert r["productos"][0]["puntuacion"] >= r["productos"][-1]["puntuacion"]
    # filtros y ordenaciones
    r2 = (await cliente.get(f"/api/v1/busquedas/{bid}/resultados?apto_24_7=true")).json()
    assert [p["nombre"] for p in r2["productos"]] and all(
        p["atributos"].get("apto_24_7") for p in r2["productos"]
    )
    r3 = (await cliente.get(f"/api/v1/busquedas/{bid}/resultados?orden=precio_asc&fuera_rango=true")).json()
    precios = [p["mejor_precio"] for p in r3["productos"]]
    assert precios == sorted(precios) and r3["total_productos"] == 5
    r4 = (await cliente.get(f"/api/v1/busquedas/{bid}/resultados?estado=nuevo")).json()
    assert all(o["estado_producto"] != "reacondicionado" for p in r4["productos"] for o in p["ofertas"])
    # repetir con precio cambiado → histórico
    b._ofertas[0]["precio"] = 169.0
    bid2 = (await cliente.post("/api/v1/busquedas", json=PETICION)).json()["id"]
    await _terminar(cliente, bid2)
    oferta = next(
        o
        for p in (await cliente.get(f"/api/v1/busquedas/{bid2}/resultados")).json()["productos"]
        for o in p["ofertas"]
        if o["url"] == "https://b.example/p/1"
    )
    st = cliente.app.state
    precios = await st.bd.todos("SELECT precio FROM precios WHERE oferta_id = ? ORDER BY id", (oferta["id"],))
    assert [p["precio"] for p in precios] == [179.0, 169.0]
    assert a.llamadas == 2
    csv = (await cliente.get(f"/api/v1/exportar/{bid2}.csv")).text
    assert "Beelink" in csv and csv.count("\n") >= 4


async def test_fuente_que_falla_degrada_a_enlace(cliente, monkeypatch):
    class Rota(AdaptadorBase):
        slug, nivel = "tienda-rota", "B"

        async def buscar(self, consulta, ctx):
            raise ValueError("HTML inesperado")

    monkeypatch.setitem(registro(), "tienda-rota", Rota())
    r = await cliente.post(
        "/api/v1/herramientas",
        json={
            "nombre": "Tienda rota",
            "url": "https://r.example",
            "url_plantilla_busqueda": "https://r.example/?q={q}",
        },
    )
    assert r.status_code == 201
    bid = (
        await cliente.post(
            "/api/v1/busquedas", json={"texto": "mini pc", "interpretar": False, "fuentes": ["tienda-rota"]}
        )
    ).json()["id"]
    d = await _terminar(cliente, bid)
    f = d["fuentes"][0]
    assert f["estado"] == "degradada" and f["nivel_usado"] == "D" and "HTML inesperado" in f["error"]
    r = (await cliente.get(f"/api/v1/busquedas/{bid}/resultados")).json()
    assert len(r["enlaces"]) == 1 and "q=mini+pc" in r["enlaces"][0]["url"]
