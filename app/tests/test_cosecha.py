from pathlib import Path
from types import SimpleNamespace

from app.dominio import OfertaCruda

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "app"
    / "fuentes"
    / "fixtures"
    / "chollometro"
    / "busqueda-minipc.html"
)


class _IA:
    def __init__(self):
        self.reparaciones = []
        self.costes = None

    def disponible(self):
        return True

    async def extraer_ofertas(self, markdown, url, fuente):
        return [
            OfertaCruda(
                url="https://js.example/p/1",
                titulo="Mini PC JS 16GB 512GB",
                precio=210.0 if "210" in markdown else 199.0,
                envio=0.0,
            )
        ]

    async def reparar(self, slug, codigo, html, error):
        self.reparaciones.append(slug)
        return SimpleNamespace(
            model_dump=lambda: {
                "diagnostico": "cambió el HTML",
                "selectores": {},
                "codigo_propuesto": "# propuesto",
                "confianza": 0.4,
            }
        )


async def test_cosecha_pendientes_y_procesado(cliente):
    st = cliente.app.state
    st.ia = _IA()
    # una herramienta con JS y una búsqueda cuya fuente quedó degradada
    r = await cliente.post(
        "/api/v1/herramientas",
        json={
            "nombre": "Tienda JS",
            "url": "https://js.example",
            "url_plantilla_busqueda": "https://js.example/s?q={q}",
            "necesita_js": True,
        },
    )
    hid = r.json()["id"]
    bid = (
        await cliente.post(
            "/api/v1/busquedas",
            json={
                "texto": "mini pc 16gb",
                "interpretar": False,
                "fuentes": ["tienda-js"],
                "usar_cache": False,
            },
        )
    ).json()["id"]
    import asyncio

    for _ in range(100):
        if (await cliente.get(f"/api/v1/busquedas/{bid}")).json()["estado"] == "terminada":
            break
        await asyncio.sleep(0.05)
    await st.bd.ejecutar(
        "UPDATE busqueda_fuentes SET estado = 'degradada', nivel_usado = 'D' WHERE busqueda_id = ?", (bid,)
    )
    p = (await cliente.get("/api/v1/tareas/cosecha/pendientes")).json()
    assert [x["slug"] for x in p["paginas"]] == ["tienda-js"] and p["paginas"][0][
        "url"
    ] == "https://js.example/s?q=mini+pc+16gb"
    assert any(x["slug"] == "chollometro" for x in p["parsers"])
    cuerpo = {
        "paginas": [{**p["paginas"][0], "markdown": "[Mini PC JS 16GB 512GB](https://js.example/p/1) 199 €"}],
        "ofertas": [],
        "parsers": [{"slug": "chollometro", "url": "x", "html": FIXTURE.read_text(encoding="utf-8")}],
    }
    r = (await cliente.post("/api/v1/tareas/cosecha", json=cuerpo)).json()
    assert (
        r["paginas_ok"] == 1
        and r["ofertas_nuevas"] == 1
        and r["parsers"]["chollometro"]["n"] == 5
        and not r["parsers"]["chollometro"]["anomalia"]
    )
    b = (await cliente.get(f"/api/v1/busquedas/{bid}")).json()
    assert b["fuentes"][0]["estado"] == "ok" and b["fuentes"][0]["nivel_usado"] == "C"
    h = next(x for x in (await cliente.get("/api/v1/herramientas")).json()["herramientas"] if x["id"] == hid)
    assert h["universal_ok"] and h["nivel"] == "C"
    # oferta vigilada: refresco de precio → histórico
    res = (await cliente.get(f"/api/v1/busquedas/{bid}/resultados")).json()
    oid = res["productos"][0]["ofertas"][0]["id"]
    await cliente.patch(f"/api/v1/ofertas/{oid}/vigilar", json={"vigilada": True})
    p = (await cliente.get("/api/v1/tareas/cosecha/pendientes")).json()
    assert [o["oferta_id"] for o in p["ofertas"]] == [oid]
    r = (
        await cliente.post(
            "/api/v1/tareas/cosecha",
            json={
                "ofertas": [{"oferta_id": oid, "url": "https://js.example/p/1", "markdown": "ahora 210 €"}]
            },
        )
    ).json()
    assert r["precios_actualizados"] == 1
    h = (await cliente.get(f"/api/v1/ofertas/{oid}/historico")).json()
    assert [x["total"] for x in h["serie"]] == [199.0, 210.0]
    # 0 anómalo en chollometro → Reparador
    r = (
        await cliente.post(
            "/api/v1/tareas/cosecha",
            json={
                "parsers": [
                    {
                        "slug": "chollometro",
                        "url": "x",
                        "html": "<html><body><p>sin resultados</p></body></html>",
                    }
                ]
            },
        )
    ).json()
    assert (
        r["parsers"]["chollometro"]["anomalia"] is True
        and st.ia.reparaciones == ["chollometro"]
        and r["reparaciones"][0]["codigo_propuesto"]
    )


async def test_copia_sqlite(cliente):
    r = await cliente.get("/api/v1/exportar/copia.sqlite")
    assert r.status_code == 200 and r.content.startswith(b"SQLite format 3")
