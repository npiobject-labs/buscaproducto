from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ..bd import ahora
from ..tareas.vigilar import historico
from . import Protegido, estado

router = APIRouter(tags=["ofertas"], dependencies=[Protegido])


@router.get("/ofertas/{oid}/historico")
async def ver_historico(oid: int, st=Depends(estado)):
    datos = await historico(st.bd, oid)
    if not datos:
        raise HTTPException(404, {"error": "no_existe"})
    return datos


@router.patch("/ofertas/{oid}/vigilar")
async def vigilar_oferta(oid: int, cuerpo: dict[str, Any], st=Depends(estado)):
    if not await st.bd.uno("SELECT 1 FROM ofertas WHERE id = ?", (oid,)):
        raise HTTPException(404, {"error": "no_existe"})
    await st.bd.ejecutar(
        "UPDATE ofertas SET vigilada = ?, ultima_vez = ultima_vez WHERE id = ?",
        (int(bool(cuerpo.get("vigilada", True))), oid),
    )
    return {"id": oid, "vigilada": bool(cuerpo.get("vigilada", True)), "desde": ahora()}
