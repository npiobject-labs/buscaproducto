"""Contador de consumo por proveedor y presupuesto mensual con corte (RF-21)."""

from __future__ import annotations

from datetime import UTC, datetime

from .bd import BD, ahora
from .config import config

# Coste unitario estimado (euros) por unidad de cada proveedor; se afina al confirmar tarifas.
COSTE_UNIDAD = {
    "serper": 0.001,  # por crédito (≈ 1 $/1.000)
    "firecrawl": 0.002,  # por página
    "keepa": 0.001,  # por token de Keepa
    "apify": 0.01,  # por unidad de cómputo estimada
    "ebay": 0.0,
    "telegram": 0.0,
}
# Anthropic: euros por millón de tokens (entrada, salida). Aproximación 1 $ ≈ 0,92 €.
COSTE_TOKENS = {
    "claude-opus-5": (4.6, 23.0),
    "claude-sonnet-5": (1.84, 9.2),
    "claude-haiku-4-5": (0.92, 4.6),
}


class Costes:
    def __init__(self, bd: BD):
        self.bd = bd

    @staticmethod
    def _inicio_mes() -> str:
        return datetime.now(UTC).strftime("%Y-%m-01T00:00:00")

    async def gasto_mes(self, proveedor: str) -> float:
        fila = await self.bd.uno(
            "SELECT COALESCE(SUM(coste_estimado), 0) AS g FROM costes_api WHERE proveedor = ? AND fecha >= ?",
            (proveedor, self._inicio_mes()),
        )
        return float(fila["g"]) if fila else 0.0

    async def permitido(self, proveedor: str) -> tuple[bool, float, float]:
        """(permitido, gastado, presupuesto). Presupuesto 0 = sin límite salvo que la clave no exista."""
        presupuesto = config.presupuesto.get(proveedor, 0.0)
        gastado = await self.gasto_mes(proveedor)
        if presupuesto <= 0:
            return True, gastado, presupuesto
        return gastado < presupuesto, gastado, presupuesto

    async def registrar(
        self, proveedor: str, unidades: float, coste: float | None = None, detalle: str | None = None
    ) -> float:
        coste = coste if coste is not None else unidades * COSTE_UNIDAD.get(proveedor, 0.0)
        await self.bd.ejecutar(
            "INSERT INTO costes_api (fecha, proveedor, unidades, coste_estimado, detalle) VALUES (?,?,?,?,?)",
            (ahora(), proveedor, unidades, coste, detalle),
        )
        presupuesto = config.presupuesto.get(proveedor, 0.0)
        if presupuesto > 0:
            gastado = await self.gasto_mes(proveedor)
            if gastado - coste < presupuesto * config.aviso_presupuesto <= gastado:
                await self.bd.evento(
                    "presupuesto al 80 %",
                    proveedor,
                    "aviso",
                    gastado=round(gastado, 3),
                    presupuesto=presupuesto,
                )
            if gastado - coste < presupuesto <= gastado:
                await self.bd.evento(
                    "presupuesto agotado",
                    proveedor,
                    "error",
                    gastado=round(gastado, 3),
                    presupuesto=presupuesto,
                )
        return coste

    async def registrar_tokens(
        self, modelo: str, entrada: int, salida: int, detalle: str | None = None
    ) -> float:
        cin, cout = COSTE_TOKENS.get(modelo, COSTE_TOKENS["claude-opus-5"])
        coste = entrada / 1e6 * cin + salida / 1e6 * cout
        return await self.registrar("anthropic", entrada + salida, coste, detalle or modelo)

    async def resumen(self) -> list[dict]:
        filas = await self.bd.todos(
            "SELECT proveedor, SUM(unidades) AS unidades, SUM(coste_estimado) AS coste, COUNT(*) AS llamadas FROM costes_api WHERE fecha >= ? GROUP BY proveedor ORDER BY coste DESC",
            (self._inicio_mes(),),
        )
        vistos = {f["proveedor"] for f in filas}
        for proveedor in config.presupuesto:
            if proveedor not in vistos:
                filas.append({"proveedor": proveedor, "unidades": 0, "coste": 0.0, "llamadas": 0})
        for f in filas:
            f["presupuesto"] = config.presupuesto.get(f["proveedor"], 0.0)
            f["coste"] = round(float(f["coste"]), 4)
        return filas
