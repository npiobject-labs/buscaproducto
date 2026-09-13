"""Configuración por variables de entorno (prefijo BP_). Todo tiene valor por defecto salvo la clave."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parent


def _int(nombre: str, defecto: int) -> int:
    try:
        return int(os.environ.get(nombre, defecto))
    except ValueError:
        return defecto


def _float(nombre: str, defecto: float) -> float:
    try:
        return float(os.environ.get(nombre, defecto))
    except ValueError:
        return defecto


@dataclass
class Config:
    clave: str = field(default_factory=lambda: os.environ.get("BP_CLAVE", ""))
    ruta_bd: Path = field(
        default_factory=lambda: Path(os.environ.get("BP_BD", "/datos/buscaproducto.sqlite"))
    )
    build_id: str = field(default_factory=lambda: os.environ.get("BUILD_ID", "dev"))
    origenes_cors: list[str] = field(
        default_factory=lambda: [
            o.strip()
            for o in os.environ.get(
                "BP_CORS", "https://npiobject-labs.github.io,http://localhost:8081,http://127.0.0.1:8081"
            ).split(",")
            if o.strip()
        ]
    )
    user_agent: str = "buscaproducto/1.0 (+https://github.com/npiobject-labs/buscaproducto)"
    # Fuentes
    fuentes_paralelas: int = field(default_factory=lambda: _int("BP_FUENTES_PARALELAS", 4))
    timeout_fuente_s: float = field(default_factory=lambda: _float("BP_TIMEOUT_FUENTE", 20.0))
    timeout_busqueda_s: float = field(default_factory=lambda: _float("BP_TIMEOUT_BUSQUEDA", 60.0))
    ttl_cache_busqueda_s: int = field(default_factory=lambda: _int("BP_TTL_CACHE", 6 * 3600))
    ttl_cache_robots_s: int = 24 * 3600
    intervalo_dominio_s: float = field(default_factory=lambda: _float("BP_INTERVALO_DOMINIO", 2.0))
    fallos_breaker: int = 3
    segundos_breaker: int = 30 * 60
    max_busquedas_en_curso: int = 5
    # Claves de terceros (todas opcionales)
    anthropic_api_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))
    serper_api_key: str = field(default_factory=lambda: os.environ.get("SERPER_API_KEY", ""))
    ebay_client_id: str = field(default_factory=lambda: os.environ.get("EBAY_CLIENT_ID", ""))
    ebay_client_secret: str = field(default_factory=lambda: os.environ.get("EBAY_CLIENT_SECRET", ""))
    firecrawl_api_key: str = field(default_factory=lambda: os.environ.get("FIRECRAWL_API_KEY", ""))
    keepa_api_key: str = field(default_factory=lambda: os.environ.get("KEEPA_API_KEY", ""))
    apify_token: str = field(default_factory=lambda: os.environ.get("APIFY_TOKEN", ""))
    telegram_bot_token: str = field(default_factory=lambda: os.environ.get("TELEGRAM_BOT_TOKEN", ""))
    telegram_chat_id: str = field(default_factory=lambda: os.environ.get("TELEGRAM_CHAT_ID", ""))
    # IA
    modelo_principal: str = field(
        default_factory=lambda: os.environ.get("BP_MODELO_PRINCIPAL", "claude-opus-5")
    )
    modelo_rapido: str = field(default_factory=lambda: os.environ.get("BP_MODELO_RAPIDO", "claude-haiku-4-5"))
    modelo_reintento: str = field(
        default_factory=lambda: os.environ.get("BP_MODELO_REINTENTO", "claude-sonnet-5")
    )
    # Presupuesto mensual por proveedor, en euros (0 = sin límite)
    presupuesto: dict[str, float] = field(
        default_factory=lambda: {
            "anthropic": _float("BP_PRESUPUESTO_ANTHROPIC", 6.0),
            "serper": _float("BP_PRESUPUESTO_SERPER", 5.0),
            "firecrawl": _float("BP_PRESUPUESTO_FIRECRAWL", 5.0),
            "keepa": _float("BP_PRESUPUESTO_KEEPA", 0.0),
            "apify": _float("BP_PRESUPUESTO_APIFY", 5.0),
        }
    )
    aviso_presupuesto: float = 0.8


config = Config()
