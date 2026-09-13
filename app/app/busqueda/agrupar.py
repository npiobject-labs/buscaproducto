"""Deduplicación y agrupación de ofertas en productos: EAN/ASIN → clave exacta; si no, similitud de títulos."""

from __future__ import annotations

import re

from rapidfuzz import fuzz

UMBRAL_IGUAL = 90
UMBRAL_DUDA = 75
_RUIDO = re.compile(
    r"\b(mini pc|minipc|ordenador|pc|computer|desktop|sobremesa|nuevo|new|oferta|envío gratis|windows\s*\d+\s*(pro)?|w11|w10|con|with|y|and|de|para|the)\b",
    re.I,
)


def titulo_canonico(titulo: str) -> str:
    t = titulo.lower()
    t = re.sub(r"[\(\)\[\]\{\}|,;:/\\\"'·•\-–—]", " ", t)
    t = _RUIDO.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def clave_canonica(
    titulo: str, marca: str | None, modelo: str | None, ean: str | None, asin: str | None
) -> str:
    if ean:
        return f"ean:{ean}"
    if asin:
        return f"asin:{asin}"
    if marca and modelo:
        return f"mm:{marca.lower()}:{modelo.lower()}"
    base = titulo_canonico(titulo)
    # nos quedamos con los 6 primeros tokens «fuertes» (marca, modelo, cpu, ram, disco)
    tokens = [t for t in base.split() if len(t) > 1][:6]
    return "t:" + " ".join(tokens)


def similitud(a: str, b: str) -> float:
    return fuzz.token_set_ratio(titulo_canonico(a), titulo_canonico(b))


def agrupar(titulos: list[tuple[int, str, str]]) -> tuple[dict[int, int], list[tuple[int, int, float]]]:
    """titulos: [(id, titulo, clave_exacta_o_vacía)] → (id→grupo, parejas dudosas (id_a, id_b, similitud))."""
    grupo: dict[int, int] = {}
    por_clave: dict[str, int] = {}
    representantes: list[tuple[int, str]] = []
    dudosas: list[tuple[int, int, float]] = []
    for oid, titulo, clave in titulos:
        if clave and clave in por_clave:
            grupo[oid] = por_clave[clave]
            continue
        asignado = None
        mejor_duda: tuple[int, float] | None = None
        for rep_id, rep_titulo in representantes:
            s = similitud(titulo, rep_titulo)
            if s >= UMBRAL_IGUAL:
                asignado = grupo[rep_id]
                break
            if s >= UMBRAL_DUDA and (mejor_duda is None or s > mejor_duda[1]):
                mejor_duda = (rep_id, s)
        if asignado is None:
            asignado = oid
            representantes.append((oid, titulo))
            if mejor_duda:
                dudosas.append((oid, mejor_duda[0], mejor_duda[1]))
        grupo[oid] = asignado
        if clave:
            por_clave[clave] = asignado
    return grupo, dudosas
