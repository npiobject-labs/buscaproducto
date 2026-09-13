"""Tarea diaria (vigilar.yml): refresca las ofertas vigiladas, apunta el histórico y dispara alertas."""

from __future__ import annotations

import html
from statistics import median
from typing import Any

from ..bd import BD, a_json, ahora, de_json
from ..busqueda import orquestador
from ..dominio import PeticionBusqueda
from ..http import Http
from . import telegram

DIAS_VIGILANCIA_TOP = 5  # búsquedas recientes cuyo top se vigila


async def historico(bd: BD, oferta_id: int) -> dict[str, Any]:
    o = await bd.uno(
        "SELECT o.*, h.nombre AS fuente_nombre, h.slug AS fuente FROM ofertas o JOIN herramientas h ON h.id = o.herramienta_id WHERE o.id = ?",
        (oferta_id,),
    )
    if not o:
        return {}
    serie = await bd.todos(
        "SELECT fecha, precio, envio FROM precios WHERE oferta_id = ? ORDER BY fecha", (oferta_id,)
    )
    valores = [p["precio"] + (p["envio"] or 0) for p in serie if p["precio"] is not None]
    actual = (o["precio"] or 0) + (o["envio"] or 0) if o["precio"] is not None else None
    # comparables: ofertas del mismo producto en otras fuentes
    comparables = (
        await bd.todos(
            "SELECT precio + COALESCE(envio, 0) AS total FROM ofertas WHERE producto_id = ? AND precio IS NOT NULL AND id != ?",
            (o["producto_id"], oferta_id),
        )
        if o["producto_id"]
        else []
    )
    otros = [c["total"] for c in comparables]
    minimo = min(valores) if valores else None
    med = median(valores + otros) if (valores + otros) else None
    veredicto, motivo = "sin_datos", "sin histórico suficiente"
    if actual is not None and med is not None:
        if minimo is not None and actual <= minimo * 1.02 and (len(valores) >= 3 or otros):
            veredicto, motivo = "buen_precio", f"en el mínimo histórico ({minimo:.2f} €)"
        elif actual <= med * 0.95:
            veredicto, motivo = (
                "buen_precio",
                f"un {100 * (1 - actual / med):.0f} % por debajo de la mediana ({med:.2f} €)",
            )
        elif actual >= med * 1.10:
            veredicto, motivo = (
                "caro",
                f"un {100 * (actual / med - 1):.0f} % por encima de la mediana ({med:.2f} €)",
            )
        else:
            veredicto, motivo = "normal", f"en línea con la mediana ({med:.2f} €)"
    return {
        "oferta": {
            k: o[k]
            for k in (
                "id",
                "url",
                "titulo",
                "precio",
                "envio",
                "vendedor",
                "fuente",
                "fuente_nombre",
                "vigilada",
                "primera_vez",
                "ultima_vez",
            )
        },
        "serie": [
            {
                "fecha": p["fecha"],
                "precio": p["precio"],
                "envio": p["envio"],
                "total": (p["precio"] or 0) + (p["envio"] or 0),
            }
            for p in serie
        ],
        "actual": actual,
        "minimo": minimo,
        "maximo": max(valores) if valores else None,
        "mediana": med,
        "n_comparables": len(otros),
        "veredicto": veredicto,
        "motivo": motivo,
    }


async def ofertas_a_vigilar(bd: BD) -> list[dict[str, Any]]:
    """Ofertas con alerta activa, marcadas `vigilada`, o del top 10 de las últimas búsquedas."""
    filas = await bd.todos(
        """SELECT DISTINCT o.id, o.url, o.titulo, o.herramienta_id, o.precio, o.envio, h.slug, b.id AS busqueda_id
           FROM ofertas o JOIN herramientas h ON h.id = o.herramienta_id
           LEFT JOIN alertas a ON a.oferta_id = o.id AND a.activa = 1
           LEFT JOIN busqueda_ofertas bo ON bo.oferta_id = o.id
           LEFT JOIN busquedas b ON b.id = bo.busqueda_id
           WHERE o.tipo = 'oferta' AND (o.vigilada = 1 OR a.id IS NOT NULL OR (bo.posicion < 10 AND b.creada >= date('now', ?)))""",
        (f"-{DIAS_VIGILANCIA_TOP} days",),
    )
    return filas


async def vigilar(bd: BD, http: Http, ia: Any = None) -> dict[str, Any]:
    """Relanza (sin caché) las búsquedas con alertas o recientes, para refrescar precios, y evalúa las alertas."""
    inicio = ahora()
    busquedas = await bd.todos(
        """SELECT DISTINCT b.* FROM busquedas b
           LEFT JOIN alertas a ON a.busqueda_id = b.id AND a.activa = 1
           WHERE b.estado = 'terminada' AND (a.id IS NOT NULL OR b.creada >= date('now', ?))
           ORDER BY b.creada DESC LIMIT 10""",
        (f"-{DIAS_VIGILANCIA_TOP} days",),
    )
    relanzadas = []
    for b in busquedas:
        inter = de_json(b["interpretacion_json"], {}) or {}
        peticion = PeticionBusqueda(
            texto=b["texto"],
            especificaciones=de_json(b["especificaciones_json"], []),
            precio_min=b["precio_min"],
            precio_max=b["precio_max"],
            estado=b["estado_producto"],
            fuentes=de_json(b["fuentes_json"], None),
            interpretar=False,
            usar_cache=False,
        )
        if inter.get("consulta_base"):
            peticion.texto = inter["consulta_base"]
        bid, _ = await orquestador.crear(bd, peticion, None)
        await bd.ejecutar(
            "UPDATE busquedas SET interpretacion_json = ? WHERE id = ?",
            (a_json({**inter, "origen": "vigilancia", "de": b["id"]}), bid),
        )
        await orquestador.ejecutar(bd, http, bid, ia)
        relanzadas.append({"de": b["id"], "nueva": bid})
        # las alertas de búsqueda siguen a la búsqueda nueva
        await bd.ejecutar(
            "UPDATE alertas SET busqueda_id = ? WHERE busqueda_id = ? AND activa = 1", (bid, b["id"])
        )
    avisos = await evaluar_alertas(bd, http)
    resumen = {"inicio": inicio, "fin": ahora(), "busquedas_relanzadas": relanzadas, "avisos": avisos}
    await bd.evento("vigilancia ejecutada", "vigilar", "info", relanzadas=len(relanzadas), avisos=len(avisos))
    return resumen


async def evaluar_alertas(bd: BD, http: Http) -> list[str]:
    avisos: list[str] = []
    for a in await bd.todos("SELECT * FROM alertas WHERE activa = 1"):
        texto = None
        if a["tipo"] == "precio_objetivo" and a["oferta_id"]:
            o = await bd.uno(
                "SELECT o.*, h.nombre AS fuente_nombre FROM ofertas o JOIN herramientas h ON h.id = o.herramienta_id WHERE o.id = ?",
                (a["oferta_id"],),
            )
            if o and o["precio"] is not None:
                total = o["precio"] + (o["envio"] or 0)
                if a["umbral"] is not None and total <= a["umbral"]:
                    texto = f"💶 <b>Precio objetivo alcanzado</b>\n{html.escape(o['titulo'][:120])}\n{total:.2f} € en {html.escape(o['fuente_nombre'])} (objetivo {a['umbral']:.2f} €)\n{html.escape(o['url'])}"
        elif a["tipo"] == "nueva_oferta" and a["busqueda_id"]:
            desde = a["ultima_comprobacion"] or a["creada"]
            nuevas = await bd.todos(
                """SELECT o.titulo, o.precio, o.envio, o.url, h.nombre AS fuente_nombre, bo.puntuacion
                   FROM busqueda_ofertas bo JOIN ofertas o ON o.id = bo.oferta_id JOIN herramientas h ON h.id = o.herramienta_id
                   WHERE bo.busqueda_id = ? AND o.tipo = 'oferta' AND o.primera_vez > ? AND bo.puntuacion >= COALESCE(?, 80)
                   ORDER BY bo.puntuacion DESC, o.precio LIMIT 5""",
                (a["busqueda_id"], desde, a["umbral"]),
            )
            if nuevas:
                lineas = [
                    f"• {html.escape(n['titulo'][:90])} · {(n['precio'] or 0) + (n['envio'] or 0):.2f} € · {html.escape(n['fuente_nombre'])} · {n['puntuacion']:.0f} pts\n{html.escape(n['url'])}"
                    for n in nuevas
                ]
                texto = "🆕 <b>Nuevas ofertas que cumplen tu búsqueda</b>\n" + "\n".join(lineas)
        await bd.ejecutar("UPDATE alertas SET ultima_comprobacion = ? WHERE id = ?", (ahora(), a["id"]))
        if texto:
            if a["ultimo_disparo"] and a["tipo"] == "precio_objetivo" and a["ultimo_disparo"] > ahora()[:10]:
                continue  # una vez al día como máximo
            enviado = await telegram.enviar(http, texto)
            await bd.ejecutar("UPDATE alertas SET ultimo_disparo = ? WHERE id = ?", (ahora(), a["id"]))
            await bd.evento(
                "alerta disparada" + ("" if enviado else " (sin Telegram)"),
                "alertas",
                "info",
                alerta=a["id"],
                tipo=a["tipo"],
            )
            avisos.append(texto)
    return avisos
