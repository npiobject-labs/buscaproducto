"""Envío de avisos por Telegram (Bot API). Sin token, no hace nada y lo registra."""

from __future__ import annotations

from ..config import config
from ..http import Http, Politica


async def enviar(http: Http, texto: str) -> bool:
    if not (config.telegram_bot_token and config.telegram_chat_id):
        await http.bd.evento(
            "Telegram no configurado: aviso no enviado", "telegram", "aviso", texto=texto[:200]
        )
        return False
    url = f"https://api.telegram.org/bot{config.telegram_bot_token}/sendMessage"
    await http.obtener(
        url,
        metodo="POST",
        json_body={
            "chat_id": config.telegram_chat_id,
            "text": texto[:4000],
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        politica=Politica(ttl_cache_s=0, respetar_robots=False, intervalo_s=0.2, timeout_s=20),
        fuente="telegram",
        usar_cache=False,
    )
    return True
