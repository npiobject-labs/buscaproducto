"""Dependencias comunes de la API: clave, rate limit y acceso al estado de la app."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import Depends, HTTPException, Request

from ..config import config

_peticiones: dict[str, deque[float]] = defaultdict(deque)
LIMITE_MIN = 120


async def requiere_clave(request: Request) -> None:
    if not config.clave:
        raise HTTPException(
            503, {"error": "sin_clave", "detalle": "El backend no tiene BP_CLAVE configurada"}
        )
    clave = request.headers.get("x-clave") or request.query_params.get("clave")
    if clave != config.clave:
        raise HTTPException(
            401, {"error": "clave_invalida", "detalle": "Cabecera X-Clave ausente o incorrecta"}
        )
    ip = request.client.host if request.client else "?"
    cola = _peticiones[ip]
    ahora = time.time()
    while cola and cola[0] < ahora - 60:
        cola.popleft()
    if len(cola) >= LIMITE_MIN:
        raise HTTPException(
            429, {"error": "demasiadas_peticiones", "detalle": f"Máximo {LIMITE_MIN} peticiones por minuto"}
        )
    cola.append(ahora)


def estado(request: Request):
    return request.app.state


Protegido = Depends(requiere_clave)
