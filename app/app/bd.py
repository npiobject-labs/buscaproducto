"""Acceso a SQLite (aiosqlite) con migraciones numeradas y utilidades comunes."""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiosqlite

from .config import RAIZ, config

CARPETA_MIGRACIONES = RAIZ / "migraciones"


def ahora() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def a_json(valor: Any) -> str:
    return json.dumps(valor, ensure_ascii=False, separators=(",", ":"))


def de_json(texto: str | None, defecto: Any = None) -> Any:
    if not texto:
        return defecto
    try:
        return json.loads(texto)
    except ValueError:
        return defecto


class BD:
    """Una conexión por proceso; SQLite serializa las escrituras de todas formas."""

    def __init__(self, ruta: Path | None = None):
        self.ruta = ruta or config.ruta_bd
        self.con: aiosqlite.Connection | None = None

    async def abrir(self) -> None:
        if self.ruta != Path(":memory:"):
            self.ruta.parent.mkdir(parents=True, exist_ok=True)
        self.con = await aiosqlite.connect(str(self.ruta))
        self.con.row_factory = aiosqlite.Row
        await self.con.execute("PRAGMA journal_mode=WAL")
        await self.con.execute("PRAGMA foreign_keys=ON")
        await self.con.execute("PRAGMA busy_timeout=5000")
        await self.migrar()

    async def cerrar(self) -> None:
        if self.con:
            await self.con.close()
            self.con = None

    @property
    def c(self) -> aiosqlite.Connection:
        assert self.con is not None, "BD no abierta"
        return self.con

    async def migrar(self) -> None:
        await self.c.execute(
            "CREATE TABLE IF NOT EXISTS migraciones (nombre TEXT PRIMARY KEY, aplicada TEXT NOT NULL)"
        )
        aplicadas = {r[0] for r in await self.c.execute_fetchall("SELECT nombre FROM migraciones")}
        for ruta in sorted(CARPETA_MIGRACIONES.glob("*.sql")):
            if ruta.name in aplicadas or not re.match(r"^\d{3}-", ruta.name):
                continue
            await self.c.executescript(ruta.read_text(encoding="utf-8"))
            await self.c.execute(
                "INSERT INTO migraciones (nombre, aplicada) VALUES (?, ?)", (ruta.name, ahora())
            )
        await self.c.commit()

    # --- utilidades ---
    async def uno(self, sql: str, params: Iterable[Any] = ()) -> dict[str, Any] | None:
        cur = await self.c.execute(sql, tuple(params))
        fila = await cur.fetchone()
        await cur.close()
        return dict(fila) if fila else None

    async def todos(self, sql: str, params: Iterable[Any] = ()) -> list[dict[str, Any]]:
        cur = await self.c.execute(sql, tuple(params))
        filas = await cur.fetchall()
        await cur.close()
        return [dict(f) for f in filas]

    async def ejecutar(self, sql: str, params: Iterable[Any] = (), commit: bool = True) -> int:
        cur = await self.c.execute(sql, tuple(params))
        ultimo = cur.lastrowid or 0
        await cur.close()
        if commit:
            await self.c.commit()
        return ultimo

    async def evento(
        self, mensaje: str, fuente: str | None = None, nivel: str = "info", **datos: Any
    ) -> None:
        await self.ejecutar(
            "INSERT INTO eventos (fecha, nivel, fuente, mensaje, datos_json) VALUES (?, ?, ?, ?, ?)",
            (ahora(), nivel, fuente, mensaje, a_json(datos) if datos else None),
        )


bd = BD()
