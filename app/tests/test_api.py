import asyncio

from app.busqueda import orquestador


async def esperar(cliente, bid: str, segundos: float = 10):
    for _ in range(int(segundos * 10)):
        r = await cliente.get(f"/api/v1/busquedas/{bid}")
        if r.json()["estado"] in ("terminada", "error"):
            return r.json()
        await asyncio.sleep(0.1)
    raise AssertionError("la búsqueda no terminó")


async def test_contratos_plantilla(cliente):
    assert (await cliente.get("/")).text == "buscaproducto backend"
    r = await cliente.get("/holamundo")
    assert r.text == "holamundo" and r.headers["access-control-allow-origin"] == "*"
    r = await cliente.get("/salud")
    assert r.json()["ok"] is True and "build" in r.json()


async def test_clave_obligatoria(cliente):
    assert (await cliente.get("/api/v1/herramientas", headers={"X-Clave": ""})).status_code == 401
    assert (await cliente.get("/api/v1/herramientas")).status_code == 200


async def test_seed_y_crud(cliente):
    r = await cliente.get("/api/v1/herramientas")
    hs = r.json()["herramientas"]
    assert len(hs) >= 30 and any(h["slug"] == "idealo" for h in hs)
    r = await cliente.post(
        "/api/v1/herramientas",
        json={
            "nombre": "Mi tienda",
            "url": "https://tienda.example",
            "url_plantilla_busqueda": "https://tienda.example/buscar?q={q}",
        },
    )
    assert r.status_code == 201, r.text
    h = r.json()
    assert h["origen"] == "usuario" and h["participa"] and h["nivel_actual"] == "D"
    r = await cliente.post(
        "/api/v1/herramientas",
        json={"nombre": "Mala", "url": "https://x", "url_plantilla_busqueda": "https://x/sin-marcador"},
    )
    assert r.status_code == 422
    r = await cliente.patch(f"/api/v1/herramientas/{h['id']}/activa", json={"activa": False})
    assert r.json()["activa"] is False
    idealo = next(x for x in hs if x["slug"] == "idealo")
    assert (await cliente.delete(f"/api/v1/herramientas/{idealo['id']}")).status_code == 403
    assert (await cliente.delete(f"/api/v1/herramientas/{h['id']}")).status_code == 204


async def test_busqueda_modo_enlace(cliente):
    r = await cliente.post(
        "/api/v1/busquedas",
        json={
            "texto": "mini pc 8gb",
            "precio_min": 130,
            "precio_max": 330,
            "fuentes": ["idealo", "amazon-es", "wallapop"],
            "interpretar": False,
        },
    )
    assert r.status_code == 202, r.text
    bid = r.json()["id"]
    b = await esperar(cliente, bid)
    assert b["estado"] == "terminada" and b["progreso"]["terminadas"] == 3
    r = await cliente.get(f"/api/v1/busquedas/{bid}/resultados")
    d = r.json()
    assert d["total_ofertas"] == 0 and len(d["enlaces"]) == 3
    assert all("mini+pc+8gb" in e["url"] for e in d["enlaces"])
    r = await cliente.get("/api/v1/busquedas")
    assert r.json()["busquedas"][0]["id"] == bid
    r = await cliente.get(f"/api/v1/exportar/{bid}.csv")
    assert r.status_code == 200 and r.text.startswith("﻿producto;")


async def test_validacion_rango(cliente):
    r = await cliente.post("/api/v1/busquedas", json={"texto": "x", "precio_min": 300, "precio_max": 100})
    assert r.status_code == 422
    assert not orquestador.TAREAS
