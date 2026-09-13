"""Lectura de resultados: filtros, ordenación, agrupación por producto y facetas."""

from __future__ import annotations

from collections import Counter
from typing import Any

from ..bd import BD, de_json

ORDENES = {"puntuacion", "precio_asc", "precio_desc", "valoracion", "mejor_relacion", "posicion"}


async def ofertas_de(bd: BD, bid: str) -> list[dict[str, Any]]:
    filas = await bd.todos(
        """SELECT o.*, bo.puntuacion, bo.explicacion_json, bo.posicion, h.slug AS fuente, h.nombre AS fuente_nombre,
                  h.categoria AS fuente_categoria, p.clave_canonica, p.nombre AS producto_nombre, p.atributos_json AS producto_atributos_json
           FROM busqueda_ofertas bo JOIN ofertas o ON o.id = bo.oferta_id JOIN herramientas h ON h.id = o.herramienta_id
           LEFT JOIN productos p ON p.id = o.producto_id WHERE bo.busqueda_id = ?""",
        (bid,),
    )
    for f in filas:
        f["atributos"] = de_json(f.pop("atributos_json"), {})
        f["producto_atributos"] = de_json(f.pop("producto_atributos_json"), {})
        f["explicacion"] = de_json(f.pop("explicacion_json"), [])
        f["precio_total"] = None if f["precio"] is None else round(f["precio"] + (f["envio"] or 0), 2)
    return filas


def _pasa(f: dict[str, Any], filtros: dict[str, Any]) -> bool:
    a = {**f["producto_atributos"], **f["atributos"]}
    pt = f["precio_total"]
    if filtros.get("precio_min") is not None and (pt is None or pt < filtros["precio_min"]):
        return False
    if filtros.get("precio_max") is not None and (pt is None or pt > filtros["precio_max"]):
        return False
    if filtros.get("ram_min") is not None and (a.get("ram_gb") or 0) < filtros["ram_min"]:
        return False
    if (
        filtros.get("almacenamiento_min") is not None
        and (a.get("almacenamiento_gb") or 0) < filtros["almacenamiento_min"]
    ):
        return False
    if filtros.get("fuentes") and f["fuente"] not in filtros["fuentes"]:
        return False
    if filtros.get("apto_24_7") and not a.get("apto_24_7"):
        return False
    if (
        filtros.get("estado")
        and filtros["estado"] != "cualquiera"
        and f["estado_producto"] not in (filtros["estado"], "desconocido")
    ):
        return False
    if filtros.get("puntuacion_min") is not None and (f["puntuacion"] or 0) < filtros["puntuacion_min"]:
        return False
    return True


def facetas(ofertas: list[dict[str, Any]]) -> dict[str, Any]:
    reales = [f for f in ofertas if f["tipo"] == "oferta"]
    precios = sorted(f["precio_total"] for f in reales if f["precio_total"] is not None)
    ram = Counter(int(({**f["producto_atributos"], **f["atributos"]}).get("ram_gb") or 0) for f in reales)
    alm = Counter(
        int(({**f["producto_atributos"], **f["atributos"]}).get("almacenamiento_gb") or 0) for f in reales
    )
    return {
        "fuentes": dict(Counter(f["fuente"] for f in reales)),
        "estado": dict(Counter(f["estado_producto"] or "desconocido" for f in reales)),
        "ram_gb": {str(k): v for k, v in sorted(ram.items()) if k},
        "almacenamiento_gb": {str(k): v for k, v in sorted(alm.items()) if k},
        "apto_24_7": sum(
            1 for f in reales if ({**f["producto_atributos"], **f["atributos"]}).get("apto_24_7")
        ),
        "precio": {
            "min": precios[0] if precios else None,
            "max": precios[-1] if precios else None,
            "mediana": precios[len(precios) // 2] if precios else None,
        },
        "total": len(reales),
        "enlaces": len(ofertas) - len(reales),
    }


def agrupar_por_producto(ofertas: list[dict[str, Any]], orden: str) -> list[dict[str, Any]]:
    grupos: dict[Any, dict[str, Any]] = {}
    for f in ofertas:
        clave = f["producto_id"] or f"o{f['id']}"
        g = grupos.setdefault(
            clave,
            {
                "producto_id": f["producto_id"],
                "nombre": f["producto_nombre"] or f["titulo"],
                "atributos": {},
                "ofertas": [],
                "imagen_url": None,
            },
        )
        g["atributos"] = {**g["atributos"], **f["producto_atributos"], **f["atributos"]}
        g["imagen_url"] = g["imagen_url"] or f["imagen_url"]
        g["ofertas"].append(
            {
                k: f[k]
                for k in (
                    "id",
                    "url",
                    "titulo",
                    "precio",
                    "envio",
                    "precio_total",
                    "moneda",
                    "estado_producto",
                    "disponibilidad",
                    "vendedor",
                    "valoracion",
                    "n_valoraciones",
                    "imagen_url",
                    "fuente",
                    "fuente_nombre",
                    "puntuacion",
                    "explicacion",
                    "primera_vez",
                    "ultima_vez",
                    "vigilada",
                )
            }
        )
    salida = []
    for g in grupos.values():
        con_precio = [o for o in g["ofertas"] if o["precio_total"] is not None]
        g["ofertas"].sort(key=lambda o: (o["precio_total"] is None, o["precio_total"] or 0))
        g["mejor_precio"] = con_precio and min(o["precio_total"] for o in con_precio) or None
        g["n_tiendas"] = len({o["fuente"] for o in g["ofertas"]})
        g["puntuacion"] = max(o["puntuacion"] or 0 for o in g["ofertas"])
        g["valoracion"] = max((o["valoracion"] or 0 for o in g["ofertas"]), default=0) or None
        g["explicacion"] = max(g["ofertas"], key=lambda o: o["puntuacion"] or 0)["explicacion"]
        g["posicion"] = (
            min(o.get("posicion", 0) for o in g["ofertas"])
            if g["ofertas"] and "posicion" in g["ofertas"][0]
            else 0
        )
        salida.append(g)
    grande = 10**9
    claves = {
        "puntuacion": lambda g: (-g["puntuacion"], g["mejor_precio"] or grande),
        "precio_asc": lambda g: (g["mejor_precio"] is None, g["mejor_precio"] or 0),
        "precio_desc": lambda g: (g["mejor_precio"] is None, -(g["mejor_precio"] or 0)),
        "valoracion": lambda g: (-(g["valoracion"] or 0), -g["puntuacion"]),
        "mejor_relacion": lambda g: (
            -(g["puntuacion"] / (g["mejor_precio"] or grande)),
            g["mejor_precio"] or grande,
        ),
        "posicion": lambda g: (g["posicion"], -g["puntuacion"]),
    }
    salida.sort(key=claves.get(orden, claves["puntuacion"]))
    return salida


async def leer(
    bd: BD, bid: str, filtros: dict[str, Any], orden: str = "puntuacion", desde: int = 0, limite: int = 50
) -> dict[str, Any]:
    todas = await ofertas_de(bd, bid)
    enlaces = [f for f in todas if f["tipo"] == "enlace"]
    reales = [f for f in todas if f["tipo"] == "oferta"]
    filtradas = [f for f in reales if _pasa(f, filtros)]
    grupos = agrupar_por_producto(filtradas, orden)
    return {
        "total_ofertas": len(reales),
        "ofertas_filtradas": len(filtradas),
        "total_productos": len(grupos),
        "productos": grupos[desde : desde + limite],
        "enlaces": [
            {
                "id": f["id"],
                "url": f["url"],
                "titulo": f["titulo"],
                "fuente": f["fuente"],
                "fuente_nombre": f["fuente_nombre"],
            }
            for f in enlaces
        ],
        "facetas": facetas(reales),
    }
