"""Puntuación 0–100 de una oferta frente a las especificaciones, con explicación por especificación."""

from __future__ import annotations

import re
from typing import Any

from ..dominio import ATRIBUTOS, Especificacion

PESO_DESCONOCIDO = 0.5  # crédito parcial cuando el atributo no está en la oferta


def _a_numero(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int | float):
        return float(v)
    if isinstance(v, str):
        m = re.search(r"\d+(?:[.,]\d+)?", v)
        return float(m.group(0).replace(",", ".")) if m else None
    return None


def _a_bool(v: Any) -> bool | None:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        t = v.strip().lower()
        if t in ("true", "sí", "si", "yes", "1"):
            return True
        if t in ("false", "no", "0"):
            return False
    if isinstance(v, int | float):
        return bool(v)
    return None


def evaluar_una(spec: Especificacion, atributos: dict[str, Any], titulo: str) -> tuple[float, str, bool]:
    """(0..1, explicación, conocido)."""
    tipo = ATRIBUTOS.get(spec.clave, ("", "", "texto"))[2]
    valor = atributos.get(spec.clave)
    etiqueta = ATRIBUTOS.get(spec.clave, (spec.clave, "", ""))[0]
    if valor is None:
        # último recurso para texto: buscar la palabra en el título
        if tipo == "texto" and isinstance(spec.valor, str) and spec.valor.lower() in titulo.lower():
            return 1.0, f"{etiqueta}: «{spec.valor}» aparece en el título", True
        return PESO_DESCONOCIDO, f"{etiqueta}: sin datos", False
    if tipo == "numero":
        v, objetivo = _a_numero(valor), _a_numero(spec.valor)
        if v is None or objetivo is None:
            return PESO_DESCONOCIDO, f"{etiqueta}: valor no numérico", False
        unidad = ATRIBUTOS.get(spec.clave, ("", "", ""))[1]
        texto = f"{etiqueta}: {v:g}{unidad} (pedido {spec.operador} {objetivo:g}{unidad})"
        if spec.operador == ">=":
            return (1.0 if v >= objetivo else max(0.0, v / objetivo) * 0.6), texto, True
        if spec.operador == "<=":
            return (1.0 if v <= objetivo else max(0.0, objetivo / v) * 0.6), texto, True
        if spec.operador == "=":
            return (1.0 if abs(v - objetivo) < 1e-6 else 0.0), texto, True
        if spec.operador == "!=":
            return (0.0 if abs(v - objetivo) < 1e-6 else 1.0), texto, True
        return (1.0 if abs(v - objetivo) <= objetivo * 0.15 else 0.4), texto, True
    if tipo == "booleano":
        v, objetivo = _a_bool(valor), _a_bool(spec.valor)
        if v is None or objetivo is None:
            return PESO_DESCONOCIDO, f"{etiqueta}: sin datos", False
        origen = atributos.get(f"{spec.clave}_origen")
        nota = (
            " (heurística)"
            if origen == "heuristica"
            else (" (investigado)" if origen == "investigador" else "")
        )
        ok = v == objetivo
        return (1.0 if ok else 0.0), f"{etiqueta}: {'sí' if v else 'no'}{nota}", True
    # texto
    v, objetivo = str(valor).lower(), str(spec.valor).lower()
    ok = objetivo in v or v in objetivo
    if spec.operador == "!=":
        ok = not ok
    return (1.0 if ok else 0.0), f"{etiqueta}: {valor}", True


def puntuar(
    specs: list[Especificacion], atributos: dict[str, Any], titulo: str
) -> tuple[float, list[dict[str, Any]]]:
    if not specs:
        return 100.0, []
    total_peso = sum(s.peso for s in specs) or 1.0
    acumulado = 0.0
    explicacion: list[dict[str, Any]] = []
    for s in specs:
        parcial, texto, conocido = evaluar_una(s, atributos, titulo)
        acumulado += parcial * s.peso
        explicacion.append(
            {
                "clave": s.clave,
                "cumple": parcial >= 0.99,
                "parcial": round(parcial, 2),
                "texto": texto,
                "conocido": conocido,
                "blando": s.blando,
            }
        )
    return round(100.0 * acumulado / total_peso, 1), explicacion
