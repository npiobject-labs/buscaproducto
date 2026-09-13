"""Lado backend del cosechador: qué visitar y qué hacer con lo cosechado."""

from __future__ import annotations

import importlib
from typing import Any
from urllib.parse import quote_plus

from ..bd import BD, ahora, de_json
from ..busqueda.orquestador import guardar_ofertas
from ..dominio import Consulta, Especificacion
from ..fuentes import registro

CONSULTA_FIXTURE = "mini pc 16gb"


async def pendientes(bd: BD) -> dict[str, Any]:
    paginas = await bd.todos(
        """SELECT bf.busqueda_id, h.id AS herramienta_id, h.slug, h.url_plantilla_busqueda, h.necesita_js, b.interpretacion_json, b.texto
           FROM busqueda_fuentes bf JOIN herramientas h ON h.id = bf.herramienta_id JOIN busquedas b ON b.id = bf.busqueda_id
           WHERE b.creada >= date('now', '-5 days') AND h.url_plantilla_busqueda IS NOT NULL AND h.activa = 1
             AND (bf.estado IN ('degradada', 'error', 'omitida') OR (h.necesita_js = 1 AND bf.nivel_usado = 'D'))
             AND h.categoria NOT IN ('asistentes_ia', 'comunidades')
           ORDER BY b.creada DESC LIMIT 25"""
    )
    salida_paginas = []
    vistas = set()
    for p in paginas:
        inter = de_json(p["interpretacion_json"], {}) or {}
        texto = inter.get("consulta_base") or p["texto"] or ""
        url = p["url_plantilla_busqueda"].replace("{q}", quote_plus(texto))
        if url in vistas or not texto:
            continue
        vistas.add(url)
        salida_paginas.append(
            {
                "busqueda_id": p["busqueda_id"],
                "herramienta_id": p["herramienta_id"],
                "slug": p["slug"],
                "url": url,
                "necesita_js": bool(p["necesita_js"]),
            }
        )
    ofertas = await bd.todos(
        """SELECT DISTINCT o.id AS oferta_id, o.url FROM ofertas o LEFT JOIN alertas a ON a.oferta_id = o.id AND a.activa = 1
           WHERE o.tipo = 'oferta' AND o.precio IS NOT NULL AND (o.vigilada = 1 OR a.id IS NOT NULL) ORDER BY o.id DESC LIMIT 40"""
    )
    parsers = []
    for slug, adaptador in registro().items():
        modulo = importlib.import_module(adaptador.__class__.__module__)
        url = getattr(modulo, "URL", None)
        if adaptador.nivel == "B" and hasattr(modulo, "parsear") and isinstance(url, str) and "{q}" in url:
            parsers.append({"slug": slug, "url": url.replace("{q}", quote_plus(CONSULTA_FIXTURE))})
    return {"paginas": salida_paginas, "ofertas": ofertas, "parsers": parsers}


async def procesar(bd: BD, ia: Any, cuerpo: dict[str, Any]) -> dict[str, Any]:
    resultado: dict[str, Any] = {
        "paginas_ok": 0,
        "ofertas_nuevas": 0,
        "precios_actualizados": 0,
        "parsers": {},
        "reparaciones": [],
        "avisos": [],
    }
    con_ia = ia is not None and ia.disponible()
    for p in cuerpo.get("paginas") or []:
        h = await bd.uno("SELECT * FROM herramientas WHERE id = ?", (p.get("herramienta_id"),))
        b = await bd.uno("SELECT * FROM busquedas WHERE id = ?", (p.get("busqueda_id"),))
        if not h or not b or not p.get("markdown"):
            continue
        if not con_ia:
            resultado["avisos"].append(f"{h['slug']}: sin IA para extraer la página")
            continue
        try:
            ofertas = await ia.extraer_ofertas(p["markdown"], p["url"], h["nombre"])
        except Exception as e:  # noqa: BLE001
            resultado["avisos"].append(f"{h['slug']}: {type(e).__name__}: {str(e)[:120]}")
            continue
        specs = [Especificacion(**s) for s in de_json(b["especificaciones_json"], [])]
        inter = de_json(b["interpretacion_json"], {}) or {}
        consulta = Consulta(
            texto=inter.get("consulta_base") or b["texto"] or "",
            especificaciones=specs,
            precio_min=b["precio_min"],
            precio_max=b["precio_max"],
            estado=b["estado_producto"],
        )
        n = await guardar_ofertas(bd, b["id"], h, [o for o in ofertas if o.precio], consulta)
        await bd.ejecutar(
            "UPDATE busqueda_fuentes SET estado = 'ok', n_ofertas = ?, nivel_usado = 'C', error = 'cosechada con navegador' WHERE busqueda_id = ? AND herramienta_id = ?",
            (n, b["id"], h["id"]),
        )
        if n and not h["universal_ok"]:
            await bd.ejecutar(
                "UPDATE herramientas SET universal_ok = 1, nivel = CASE WHEN nivel = 'D' THEN 'C' ELSE nivel END WHERE id = ?",
                (h["id"],),
            )
        resultado["paginas_ok"] += 1
        resultado["ofertas_nuevas"] += n
    for o in cuerpo.get("ofertas") or []:
        fila = await bd.uno("SELECT * FROM ofertas WHERE id = ?", (o.get("oferta_id"),))
        if not fila or not o.get("markdown") or not con_ia:
            continue
        try:
            extraidas = await ia.extraer_ofertas(o["markdown"], o["url"], "página de producto")
        except Exception as e:  # noqa: BLE001
            resultado["avisos"].append(f"oferta {fila['id']}: {type(e).__name__}")
            continue
        candidata = next((x for x in extraidas if x.precio), None)
        if candidata is None:
            continue
        if fila["precio"] != candidata.precio or (fila["envio"] or 0) != (candidata.envio or 0):
            await bd.ejecutar(
                "UPDATE ofertas SET precio = ?, envio = COALESCE(?, envio), ultima_vez = ? WHERE id = ?",
                (candidata.precio, candidata.envio, ahora(), fila["id"]),
            )
            await bd.ejecutar(
                "INSERT INTO precios (oferta_id, fecha, precio, envio) VALUES (?,?,?,?)",
                (fila["id"], ahora(), candidata.precio, candidata.envio),
            )
            resultado["precios_actualizados"] += 1
        else:
            await bd.ejecutar("UPDATE ofertas SET ultima_vez = ? WHERE id = ?", (ahora(), fila["id"]))
    for pr in cuerpo.get("parsers") or []:
        slug = pr.get("slug")
        adaptador = registro().get(slug)
        if adaptador is None:
            continue
        modulo = importlib.import_module(adaptador.__class__.__module__)
        html = pr.get("html") or ""
        if not html:
            resultado["parsers"][slug] = {"n": 0, "motivo": pr.get("motivo") or "sin html", "anomalia": False}
            continue
        try:
            n = len(modulo.parsear(html))
        except Exception as e:  # noqa: BLE001
            n, error = 0, f"{type(e).__name__}: {str(e)[:200]}"
        else:
            error = "0 resultados con HTML no vacío" if n == 0 else ""
        media = await bd.uno(
            "SELECT AVG(n_ofertas) AS m, COUNT(*) AS c FROM fuente_stats WHERE slug = ? AND fecha >= date('now', '-14 days') AND estado = 'ok'",
            (slug,),
        )
        anomalia = n == 0 and bool(media and media["c"] and (media["m"] or 0) > 0)
        await bd.ejecutar(
            "INSERT INTO fuente_stats (slug, fecha, n_ofertas, estado) VALUES (?,?,?,?)",
            (slug, ahora(), n, "ok" if n else "error"),
        )
        resultado["parsers"][slug] = {"n": n, "anomalia": anomalia, "error": error}
        if anomalia:
            await bd.evento(
                "0 resultados anómalo en un adaptador con parser",
                slug,
                "error",
                media=media["m"],
                error=error,
            )
            if con_ia:
                try:
                    codigo = Path(modulo.__file__) if hasattr(modulo, "__file__") else None
                    fuente = codigo.read_text(encoding="utf-8") if codigo else ""
                    rep = await ia.reparar(slug, fuente, html, error)
                    if rep:
                        resultado["reparaciones"].append({"slug": slug, **rep.model_dump()})
                except Exception as e:  # noqa: BLE001
                    resultado["avisos"].append(f"reparador {slug}: {type(e).__name__}: {str(e)[:120]}")
    await bd.evento(
        "cosecha procesada",
        "cosecha",
        "info",
        **{
            k: v
            for k, v in resultado.items()
            if k in ("paginas_ok", "ofertas_nuevas", "precios_actualizados")
        },
    )
    return resultado


from pathlib import Path  # noqa: E402
