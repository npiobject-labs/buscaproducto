from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..bd import ahora
from . import Protegido, estado

router = APIRouter(prefix="/alertas", tags=["alertas"], dependencies=[Protegido])


class AlertaEntrada(BaseModel):
    tipo: Literal["precio_objetivo", "nueva_oferta"]
    oferta_id: int | None = None
    busqueda_id: str | None = None
    umbral: float | None = Field(default=None, ge=0)
    canal: str = "telegram"


@router.get("")
async def listar(st=Depends(estado)):
    filas = await st.bd.todos(
        """SELECT a.*, o.titulo AS oferta_titulo, o.precio AS oferta_precio, o.url AS oferta_url, b.texto AS busqueda_texto
           FROM alertas a LEFT JOIN ofertas o ON o.id = a.oferta_id LEFT JOIN busquedas b ON b.id = a.busqueda_id ORDER BY a.creada DESC"""
    )
    for f in filas:
        f["activa"] = bool(f["activa"])
    return {"alertas": filas}


@router.post("", status_code=201)
async def crear(entrada: AlertaEntrada, st=Depends(estado)):
    if entrada.tipo == "precio_objetivo":
        if not entrada.oferta_id or entrada.umbral is None:
            raise HTTPException(
                422, {"error": "faltan_datos", "detalle": "precio_objetivo necesita oferta_id y umbral"}
            )
        if not await st.bd.uno("SELECT 1 FROM ofertas WHERE id = ?", (entrada.oferta_id,)):
            raise HTTPException(404, {"error": "oferta_no_existe"})
        await st.bd.ejecutar("UPDATE ofertas SET vigilada = 1 WHERE id = ?", (entrada.oferta_id,))
    else:
        if not entrada.busqueda_id:
            raise HTTPException(
                422, {"error": "faltan_datos", "detalle": "nueva_oferta necesita busqueda_id"}
            )
        if not await st.bd.uno("SELECT 1 FROM busquedas WHERE id = ?", (entrada.busqueda_id,)):
            raise HTTPException(404, {"error": "busqueda_no_existe"})
    aid = await st.bd.ejecutar(
        "INSERT INTO alertas (tipo, busqueda_id, oferta_id, umbral, canal, activa, creada) VALUES (?,?,?,?,?,1,?)",
        (entrada.tipo, entrada.busqueda_id, entrada.oferta_id, entrada.umbral, entrada.canal, ahora()),
    )
    return await st.bd.uno("SELECT * FROM alertas WHERE id = ?", (aid,))


@router.delete("/{aid}", status_code=204)
async def borrar(aid: int, st=Depends(estado)):
    if not await st.bd.uno("SELECT 1 FROM alertas WHERE id = ?", (aid,)):
        raise HTTPException(404, {"error": "no_existe"})
    await st.bd.ejecutar("DELETE FROM alertas WHERE id = ?", (aid,))
