"""Extracción de atributos por reglas (regex) a partir de título y texto extra. La IA solo entra donde esto falla."""

from __future__ import annotations

import re
from typing import Any

_NUM = r"(\d+(?:[.,]\d+)?)"

PATRONES: list[tuple[str, re.Pattern[str], str]] = [
    ("ram_gb", re.compile(rf"\b{_NUM}\s*GB\s*(?:de\s*)?(?:RAM|DDR\d?|LPDDR\d?|memoria)", re.I), "numero"),
    ("ram_gb", re.compile(rf"\bRAM\s*(?:de\s*)?{_NUM}\s*GB", re.I), "numero"),
    ("ram_gb", re.compile(rf"\b{_NUM}\s*GB\s*\+\s*{_NUM}\s*(?:GB|TB)", re.I), "numero"),  # «16GB+512GB»
    (
        "almacenamiento_gb",
        re.compile(
            rf"\b{_NUM}\s*(TB|GB)\s*(?:de\s*)?(?:SSD|NVMe|M\.2|eMMC|HDD|disco|almacenamiento|storage|ROM)",
            re.I,
        ),
        "almacenamiento",
    ),
    (
        "almacenamiento_gb",
        re.compile(rf"\b(?:SSD|NVMe|eMMC|HDD|disco|ROM)\s*(?:de\s*)?{_NUM}\s*(TB|GB)", re.I),
        "almacenamiento",
    ),
    (
        "almacenamiento_gb",
        re.compile(rf"\b{_NUM}\s*GB\s*\+\s*{_NUM}\s*(TB|GB)", re.I),
        "almacenamiento_segundo",
    ),
    ("tdp_w", re.compile(rf"\b{_NUM}\s*W\b(?!i)", re.I), "numero"),
    ("pantalla_pulgadas", re.compile(rf"\b{_NUM}\s*(?:\"|”|''|pulgadas|inch|in\b)", re.I), "numero"),
    (
        "cpu",
        re.compile(
            r"\b((?:Intel\s+)?(?:Core\s+)?(?:i[3579]|Ultra\s*[579]|N\d{2,4}|Celeron\s+\w+|Pentium\s+\w+|Xeon\s+[\w-]+)(?:[- ]\d{4,5}[A-Z]{0,2})?|(?:AMD\s+)?Ryzen\s+[3579]\s*(?:PRO\s+)?\d{4}[A-Z]{0,3}|Apple\s+M[1-4](?:\s+(?:Pro|Max|Ultra))?|Snapdragon\s+X\s*\w+)",
            re.I,
        ),
        "texto",
    ),
    ("wifi", re.compile(r"\b(Wi-?Fi\s*(?:6E|6|7|5)|802\.11\s*[a-z]{1,2})\b", re.I), "texto"),
    (
        "ethernet_gbps",
        re.compile(rf"\b{_NUM}\s*(?:G|Gb|Gbps|GbE)\b\s*(?:LAN|Ethernet|RJ45)?", re.I),
        "numero",
    ),
    (
        "resolucion",
        re.compile(
            r"\b(4K|UHD|QHD|WQHD|2K|FHD|Full\s*HD|1920\s*x\s*1080|2560\s*x\s*1440|3840\s*x\s*2160)\b", re.I
        ),
        "texto",
    ),
]

BOOLEANOS = {
    "fanless": re.compile(r"\b(fanless|sin ventilador|pasivo|passive cooling)\b", re.I),
    "openwrt": re.compile(r"\b(openwrt|open-wrt)\b", re.I),
    "pantalla_mate": re.compile(r"\b(mate|matte|anti-?glare|antirreflej)", re.I),
}

MARCAS = [
    "Beelink",
    "Minisforum",
    "GMKtec",
    "Intel NUC",
    "Geekom",
    "ASUS",
    "Acer",
    "Lenovo",
    "HP",
    "Dell",
    "Apple",
    "MSI",
    "Gigabyte",
    "Zotac",
    "Chuwi",
    "Trigkey",
    "ACEMAGIC",
    "Ace Magician",
    "NiPoGi",
    "Kamrui",
    "Bmax",
    "Xiaomi",
    "Samsung",
    "Huawei",
    "Honor",
    "LG",
    "Sony",
    "TP-Link",
    "GL.iNet",
    "Netgear",
    "Ubiquiti",
    "MikroTik",
    "Banana Pi",
    "Raspberry Pi",
    "Odroid",
    "Fujitsu",
    "Topton",
    "Bosgame",
    "Ninkear",
    "Kingdel",
    "Qotom",
    "Protectli",
    "Cwwk",
]
_RE_MARCAS = re.compile(r"\b(" + "|".join(re.escape(m) for m in MARCAS) + r")\b", re.I)


def _num(texto: str) -> float:
    return float(texto.replace(",", "."))


def extraer(titulo: str, texto_extra: str | None = None) -> dict[str, Any]:
    texto = f"{titulo} {texto_extra or ''}"
    at: dict[str, Any] = {}
    for clave, patron, tipo in PATRONES:
        if clave in at:
            continue
        m = patron.search(texto)
        if not m:
            continue
        if tipo == "numero":
            v = _num(m.group(1))
            if clave == "ram_gb" and v > 256:
                continue
            if clave == "tdp_w" and not 3 <= v <= 500:
                continue
            if clave == "pantalla_pulgadas" and not 5 <= v <= 60:
                continue
            at[clave] = v
        elif tipo == "almacenamiento":
            v = _num(m.group(1))
            at[clave] = v * 1024 if m.group(2).upper() == "TB" else v
        elif tipo == "almacenamiento_segundo":
            v = _num(m.group(2))
            at[clave] = v * 1024 if m.group(3).upper() == "TB" else v
        else:
            at[clave] = re.sub(r"\s+", " ", m.group(1)).strip()
    for clave, patron in BOOLEANOS.items():
        if patron.search(texto):
            at[clave] = True
    m = _RE_MARCAS.search(texto)
    if m:
        at["marca"] = m.group(1)
    # Heurística 24/7: TDP bajo o pasivo → apto; se marca como heurística para que el Investigador pueda revisarla.
    if at.get("fanless") or (at.get("tdp_w") and at["tdp_w"] <= 25):
        at.setdefault("apto_24_7", True)
        at["apto_24_7_origen"] = "heuristica"
    return at


def formato_desde_texto(texto: str) -> str | None:
    t = texto.lower()
    if re.search(r"\bmini\s*-?pc\b|\bnuc\b|\btinyminimicro\b|\bsff\b", t):
        return "minipc"
    if re.search(r"\bport[aá]til\b|\blaptop\b|\bnotebook\b|\bultrabook\b", t):
        return "portatil"
    if re.search(r"\brouter\b", t):
        return "router"
    if re.search(r"\bmonitor\b", t):
        return "monitor"
    return None
