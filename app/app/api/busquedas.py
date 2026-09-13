from __future__ import annotations

import csv
import io
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse

from ..bd import de_json
from ..busqueda import orquestador, resultados
from ..dominio import PeticionBusqueda
from . import Protegido, estado

router = APIRouter(tags=["busquedas"], dependencies=[Protegido])


@router.post("/busquedas", status_code=202)
async def crear(peticion: PeticionBusqueda, st=Depends(estado)):
    if not peticion.texto and not peticion.especificaciones:
        raise HTTPException(
            422, {"error": "vacia", "detalle": "Indica un texto o al menos una especificación"}
        )
    if len(orquestador.TAREAS) >= 5:
        raise HTTPException(
            429, {"error": "ocupado", "detalle": "Hay demasiadas búsquedas en curso; espera unos segundos"}
        )
    bid, interpretacion = await orquestador.crear(st.bd, peticion, st.ia)
    orquestador.lanzar(st.bd, st.http, bid, st.ia)
    return {"id": bid, "interpretacion": interpretacion}


@router.get("/busquedas")
async def historial(limite: int = Query(20, ge=1, le=200), st=Depends(estado)):
    filas = await st.bd.todos(
        "SELECT b.id, b.texto, b.especificaciones_json, b.precio_min, b.precio_max, b.estado, b.creada, b.terminada, (SELECT COUNT(*) FROM busqueda_ofertas bo JOIN ofertas o ON o.id = bo.oferta_id WHERE bo.busqueda_id = b.id AND o.tipo = 'oferta') AS n_ofertas FROM busquedas b ORDER BY b.creada DESC LIMIT ?",
        (limite,),
    )
    for f in filas:
        f["especificaciones"] = de_json(f.pop("especificaciones_json"), [])
    return {"busquedas": filas}


async def _busqueda(st, bid: str) -> dict[str, Any]:
    b = await st.bd.uno("SELECT * FROM busquedas WHERE id = ?", (bid,))
    if not b:
        raise HTTPException(404, {"error": "no_existe"})
    return b


@router.get("/busquedas/{bid}")
async def ver(bid: str, st=Depends(estado)):
    b = await _busqueda(st, bid)
    fuentes = await st.bd.todos(
        "SELECT bf.slug, h.nombre, h.categoria, bf.estado, bf.n_ofertas, bf.error, bf.ms, bf.desde_cache, bf.nivel_usado FROM busqueda_fuentes bf JOIN herramientas h ON h.id = bf.herramienta_id WHERE bf.busqueda_id = ? ORDER BY h.categoria, h.nombre",
        (bid,),
    )
    todas = await resultados.ofertas_de(st.bd, bid)
    inter = de_json(b["interpretacion_json"], {}) or {}
    return {
        "id": bid,
        "texto": b["texto"],
        "especificaciones": de_json(b["especificaciones_json"], []),
        "precio_min": b["precio_min"],
        "precio_max": b["precio_max"],
        "estado_producto": b["estado_producto"],
        "estado": b["estado"],
        "error": b["error"],
        "creada": b["creada"],
        "terminada": b["terminada"],
        "interpretacion": inter,
        "fuentes": fuentes,
        "progreso": {
            "total": len(fuentes),
            "terminadas": sum(1 for f in fuentes if f["estado"] not in ("pendiente", "en_curso")),
        },
        "facetas": resultados.facetas(todas),
    }


@router.get("/busquedas/{bid}/resultados")
async def ver_resultados(
    bid: str,
    orden: str = "puntuacion",
    desde: int = Query(0, ge=0),
    limite: int = Query(50, ge=1, le=500),
    precio_min: float | None = None,
    precio_max: float | None = None,
    ram_min: float | None = None,
    almacenamiento_min: float | None = None,
    fuentes: str | None = None,
    apto_24_7: bool = False,
    estado: str | None = None,
    puntuacion_min: float | None = None,
    fuera_rango: bool = False,
    st=Depends(estado),
):
    b = await _busqueda(st, bid)
    filtros: dict[str, Any] = {
        "precio_min": precio_min if precio_min is not None else (None if fuera_rango else b["precio_min"]),
        "precio_max": precio_max if precio_max is not None else (None if fuera_rango else b["precio_max"]),
        "ram_min": ram_min,
        "almacenamiento_min": almacenamiento_min,
        "fuentes": [f for f in (fuentes or "").split(",") if f] or None,
        "apto_24_7": apto_24_7,
        "estado": estado,
        "puntuacion_min": puntuacion_min,
    }
    salida = await resultados.leer(
        st.bd, bid, filtros, orden if orden in resultados.ORDENES else "puntuacion", desde, limite
    )
    salida["estado"] = b["estado"]
    return salida


@router.get("/exportar/{bid}.csv")
async def exportar_csv(bid: str, st=Depends(estado)):
    await _busqueda(st, bid)
    datos = await resultados.leer(st.bd, bid, {}, "puntuacion", 0, 10_000)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(
        [
            "producto",
            "fuente",
            "titulo",
            "precio",
            "envio",
            "total",
            "estado",
            "puntuacion",
            "ram_gb",
            "almacenamiento_gb",
            "cpu",
            "apto_24_7",
            "url",
        ]
    )
    for g in datos["productos"]:
        a = g["atributos"]
        for o in g["ofertas"]:
            w.writerow(
                [
                    g["nombre"],
                    o["fuente_nombre"],
                    o["titulo"],
                    o["precio"],
                    o["envio"],
                    o["precio_total"],
                    o["estado_producto"],
                    o["puntuacion"],
                    a.get("ram_gb"),
                    a.get("almacenamiento_gb"),
                    a.get("cpu"),
                    a.get("apto_24_7"),
                    o["url"],
                ]
            )
    buf.seek(0)
    return StreamingResponse(
        iter([("﻿" + buf.getvalue()).encode()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="busqueda-{bid}.csv"'},
    )


@router.post("/interpretar")
async def interpretar(cuerpo: dict[str, Any], st=Depends(estado)):
    texto = (cuerpo.get("texto") or "").strip()
    if not texto:
        raise HTTPException(422, {"error": "vacia"})
    if st.ia is None or not st.ia.disponible():
        return {
            "disponible": False,
            "interpretacion": None,
            "motivo": "IA no configurada (falta ANTHROPIC_API_KEY) o presupuesto agotado",
        }
    inter = await st.ia.interpretar(texto)
    return {"disponible": True, "interpretacion": inter.model_dump() if inter else None}
