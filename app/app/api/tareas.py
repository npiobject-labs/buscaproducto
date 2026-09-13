from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..tareas import cosecha_backend, telegram, vigilar
from . import Protegido, estado

router = APIRouter(prefix="/tareas", tags=["tareas"], dependencies=[Protegido])


@router.get("/cosecha/pendientes")
async def cosecha_pendientes(st=Depends(estado)):
    return await cosecha_backend.pendientes(st.bd)


@router.post("/cosecha")
async def cosecha_procesar(cuerpo: dict[str, Any], st=Depends(estado)):
    return await cosecha_backend.procesar(st.bd, st.ia, cuerpo)


@router.post("/vigilar")
async def ejecutar_vigilancia(st=Depends(estado)):
    return await vigilar.vigilar(st.bd, st.http, st.ia)


@router.post("/probar-telegram")
async def probar_telegram(cuerpo: dict[str, Any] | None = None, st=Depends(estado)):
    ok = await telegram.enviar(
        st.http, (cuerpo or {}).get("texto") or "✅ buscaproducto: Telegram configurado"
    )
    return {"enviado": ok}
