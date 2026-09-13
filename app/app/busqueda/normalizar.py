"""Normalización de ofertas crudas: precios, estado, URL canónica y hash."""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

PARAMETROS_RUIDO = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "ref",
    "ref_",
    "tag",
    "fbclid",
    "gclid",
    "mkevt",
    "mkcid",
    "mkrid",
    "campid",
    "toolid",
    "hash",
    "_trkparms",
    "_trksid",
}


def parsear_precio(texto: str | float | int | None) -> float | None:
    """'1.299,00 €' → 1299.0 · '299.99' → 299.99 · '1,299.00' → 1299.0 · '129 €' → 129.0."""
    if texto is None:
        return None
    if isinstance(texto, int | float):
        return float(texto)
    t = re.sub(r"[^\d,.\-]", "", str(texto)).strip()
    if not t or t in ("-", ".", ","):
        return None
    if "," in t and "." in t:
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
    elif "," in t:
        partes = t.split(",")
        t = t.replace(",", ".") if len(partes[-1]) in (1, 2) else t.replace(",", "")
    elif t.count(".") > 1 or (t.count(".") == 1 and len(t.split(".")[-1]) == 3):
        t = t.replace(".", "")
    try:
        v = float(t)
    except ValueError:
        return None
    return v if 0 < v < 1_000_000 else None


def normalizar_estado(texto: str | None) -> str:
    t = (texto or "").lower()
    if not t:
        return "desconocido"
    if any(
        p in t
        for p in ("reacond", "refurb", "renewed", "certified", "warehouse", "outlet", "open box", "abierto")
    ):
        return "reacondicionado"
    if any(p in t for p in ("usado", "used", "segunda mano", "pre-owned", "second hand", "seminuevo")):
        return "segunda_mano"
    if any(p in t for p in ("nuevo", "new", "brand", "neu")):
        return "nuevo"
    return "desconocido"


def url_canonica(url: str) -> str:
    partes = urlsplit(url.strip())
    consulta = [
        (k, v)
        for k, v in parse_qsl(partes.query, keep_blank_values=False)
        if k.lower() not in PARAMETROS_RUIDO
    ]
    ruta = re.sub(r"/+$", "", partes.path) or "/"
    return urlunsplit(
        (partes.scheme.lower() or "https", partes.netloc.lower(), ruta, urlencode(sorted(consulta)), "")
    )


def hash_oferta(herramienta_id: int, url: str) -> str:
    return hashlib.sha1(f"{herramienta_id}|{url_canonica(url)}".encode()).hexdigest()


def limpiar_titulo(titulo: str) -> str:
    t = re.sub(r"\s+", " ", titulo).strip()
    return t[:300]
