from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse

from ..bd import de_json
from ..config import config
from . import Protegido, estado

router = APIRouter(tags=["sistema"], dependencies=[Protegido])


@router.get("/salud-bd")
async def salud_bd(st=Depends(estado)):
    n = await st.bd.uno("SELECT COUNT(*) AS n FROM herramientas")
    return {"ok": True, "herramientas": n["n"], "bd": str(st.bd.ruta), "build": config.build_id}


@router.get("/eventos")
async def eventos(
    desde: int = Query(0, ge=0),
    limite: int = Query(100, ge=1, le=500),
    nivel: str | None = None,
    st=Depends(estado),
):
    filas = await st.bd.todos(
        "SELECT * FROM eventos WHERE id > ? AND (? IS NULL OR nivel = ?) ORDER BY id DESC LIMIT ?",
        (desde, nivel, nivel, limite),
    )
    for f in filas:
        f["datos"] = de_json(f.pop("datos_json"), None)
    return {"eventos": filas}


@router.get("/costes")
async def costes(st=Depends(estado)):
    return {
        "mes": await st.costes.resumen(),
        "claves": {
            "anthropic": bool(config.anthropic_api_key),
            "serper": bool(config.serper_api_key),
            "ebay": bool(config.ebay_client_id and config.ebay_client_secret),
            "firecrawl": bool(config.firecrawl_api_key),
            "keepa": bool(config.keepa_api_key),
            "apify": bool(config.apify_token),
            "telegram": bool(config.telegram_bot_token and config.telegram_chat_id),
        },
    }


@router.get("/estado")
async def estado_general(st=Depends(estado)):
    fuentes = await st.bd.todos(
        "SELECT slug, COUNT(*) AS consultas, SUM(CASE WHEN estado = 'ok' THEN 1 ELSE 0 END) AS ok, AVG(n_ofertas) AS media_ofertas, MAX(fecha) AS ultima FROM fuente_stats GROUP BY slug ORDER BY slug"
    )
    return {
        "build": config.build_id,
        "fuentes": fuentes,
        "breaker": {
            d: {"fallos": e.fallos, "abierto": e.abierto_hasta > 0} for d, e in st.http.dominios.items()
        },
    }


@router.get("/exportar/copia.sqlite")
async def copia_sqlite(st=Depends(estado)):
    """Copia consistente de la BD (VACUUM INTO) para la copia de seguridad diaria de vigilar.yml."""
    destino = Path(tempfile.gettempdir()) / f"copia-{config.build_id[:7]}.sqlite"
    if destino.exists():
        destino.unlink()
    await st.bd.c.execute("VACUUM INTO ?", (str(destino),))
    return FileResponse(str(destino), media_type="application/vnd.sqlite3", filename="buscaproducto.sqlite")
