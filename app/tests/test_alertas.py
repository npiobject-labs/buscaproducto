import asyncio

import respx

from app.dominio import OfertaCruda
from app.fuentes import AdaptadorBase, registro


class _Tienda(AdaptadorBase):
    slug, nivel = "tienda-v", "A"
    precio = 200.0

    async def buscar(self, consulta, ctx):
        return [
            OfertaCruda(
                url="https://v.example/p/1",
                titulo="Beelink Mini S12 Pro N100 16GB 500GB",
                precio=_Tienda.precio,
                envio=0.0,
            ),
            OfertaCruda(url="https://v.example/p/2", titulo="Otro Mini PC 8GB 256GB", precio=150.0),
        ]


async def _terminar(cliente, bid):
    for _ in range(100):
        d = (await cliente.get(f"/api/v1/busquedas/{bid}")).json()
        if d["estado"] in ("terminada", "error"):
            return d
        await asyncio.sleep(0.05)
    raise AssertionError("no terminó")


async def test_historico_alertas_y_vigilancia(cliente, monkeypatch):
    monkeypatch.setitem(registro(), "tienda-v", _Tienda())
    assert (
        await cliente.post(
            "/api/v1/herramientas",
            json={
                "nombre": "Tienda V",
                "url": "https://v.example",
                "url_plantilla_busqueda": "https://v.example/?q={q}",
            },
        )
    ).status_code == 201
    peticion = {
        "texto": "mini pc",
        "especificaciones": [{"clave": "ram_gb", "operador": ">=", "valor": 16}],
        "interpretar": False,
        "fuentes": ["tienda-v"],
        "usar_cache": False,
    }
    bid = (await cliente.post("/api/v1/busquedas", json=peticion)).json()["id"]
    await _terminar(cliente, bid)
    productos = (await cliente.get(f"/api/v1/busquedas/{bid}/resultados")).json()["productos"]
    oferta = next(o for p in productos for o in p["ofertas"] if o["url"] == "https://v.example/p/1")
    h = (await cliente.get(f"/api/v1/ofertas/{oferta['id']}/historico")).json()
    assert h["actual"] == 200.0 and h["veredicto"] in ("sin_datos", "normal") and len(h["serie"]) == 1
    # alertas
    r = await cliente.post(
        "/api/v1/alertas", json={"tipo": "precio_objetivo", "oferta_id": oferta["id"], "umbral": 180}
    )
    assert r.status_code == 201, r.text
    r = await cliente.post("/api/v1/alertas", json={"tipo": "nueva_oferta", "busqueda_id": bid, "umbral": 50})
    assert r.status_code == 201
    assert len((await cliente.get("/api/v1/alertas")).json()["alertas"]) == 2
    assert (
        await cliente.post("/api/v1/alertas", json={"tipo": "precio_objetivo", "oferta_id": oferta["id"]})
    ).status_code == 422
    # baja el precio y vigila: histórico nuevo + alerta disparada (Telegram simulado)
    _Tienda.precio = 170.0
    from app import config as c

    monkeypatch.setattr(c.config, "telegram_bot_token", "123:abc")
    monkeypatch.setattr(c.config, "telegram_chat_id", "42")
    with respx.mock(assert_all_called=True) as m:
        ruta = m.post("https://api.telegram.org/bot123:abc/sendMessage").respond(200, json={"ok": True})
        r = await cliente.post("/api/v1/tareas/vigilar")
    assert r.status_code == 200, r.text
    d = r.json()
    assert (
        len(d["busquedas_relanzadas"]) == 1 and len(d["avisos"]) >= 1 and "Precio objetivo" in d["avisos"][0]
    )
    assert ruta.called
    h = (await cliente.get(f"/api/v1/ofertas/{oferta['id']}/historico")).json()
    assert [p["total"] for p in h["serie"]] == [200.0, 170.0] and h["veredicto"] == "buen_precio"
    # comparador sin IA: tabla determinista
    ids = [p["producto_id"] for p in productos][:2]
    r = await cliente.post("/api/v1/comparar", json={"producto_ids": ids})
    assert (
        r.status_code == 200 and r.json()["tabla"][0]["atributo"] == "mejor_precio" and r.json()["ia"] is None
    )
    r = await cliente.get(f"/api/v1/productos/{ids[0]}/informe")
    assert r.json()["informe"] is None
    assert (await cliente.post(f"/api/v1/productos/{ids[0]}/informe")).status_code == 503
    r = await cliente.delete(
        f"/api/v1/alertas/{(await cliente.get('/api/v1/alertas')).json()['alertas'][0]['id']}"
    )
    assert r.status_code == 204
