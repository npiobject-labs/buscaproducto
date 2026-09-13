"""Punto de entrada: contratos de la plantilla (/, /salud, /holamundo) + API /api/v1."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, PlainTextResponse

from .api import busquedas, herramientas, sistema
from .bd import BD, ahora
from .config import RAIZ, config
from .costes import Costes
from .http import Http

SEED = RAIZ / "seed" / "herramientas.json"


async def sembrar(bd: BD, ruta: Path = SEED) -> int:
    """Inserta las predefinidas que falten y actualiza sus datos sin tocar `activa` ni `universal_ok`."""
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    n = 0
    for h in datos:
        existente = await bd.uno("SELECT id FROM herramientas WHERE slug = ?", (h["slug"],))
        if existente:
            await bd.ejecutar(
                "UPDATE herramientas SET nombre=?, categoria=?, url=?, url_plantilla_busqueda=?, tipo_acceso=?, coste=?, descripcion=?, nivel=CASE WHEN universal_ok=1 AND ? = 'D' THEN 'C' ELSE ? END, politica_scraping=?, actualizada=? WHERE id=? AND origen='predefinida'",
                (
                    h["nombre"],
                    h["categoria"],
                    h["url"],
                    h["url_plantilla_busqueda"],
                    h["tipo_acceso"],
                    h["coste"],
                    h["descripcion"],
                    h["nivel"],
                    h["nivel"],
                    h["politica_scraping"],
                    ahora(),
                    existente["id"],
                ),
                commit=False,
            )
        else:
            await bd.ejecutar(
                "INSERT INTO herramientas (slug, nombre, categoria, url, url_plantilla_busqueda, tipo_acceso, coste, descripcion, origen, activa, nivel, politica_scraping, creada, actualizada) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    h["slug"],
                    h["nombre"],
                    h["categoria"],
                    h["url"],
                    h["url_plantilla_busqueda"],
                    h["tipo_acceso"],
                    h["coste"],
                    h["descripcion"],
                    "predefinida",
                    int(h["participa"]),
                    h["nivel"],
                    h["politica_scraping"],
                    ahora(),
                    ahora(),
                ),
                commit=False,
            )
            n += 1
    await bd.c.commit()
    return n


def crear_ia(bd: BD, costes: Costes, http: Http):
    try:
        from .ia import Agentes
    except ImportError:
        return None
    return Agentes(bd, costes, http)


@asynccontextmanager
async def ciclo_vida(app: FastAPI):
    bd = BD()
    await bd.abrir()
    await sembrar(bd)
    http = Http(bd)
    costes = Costes(bd)
    app.state.bd, app.state.http, app.state.costes = bd, http, costes
    app.state.ia = crear_ia(bd, costes, http)
    print(f"buscaproducto backend · build {config.build_id} · bd {bd.ruta}")
    try:
        yield
    finally:
        await http.cerrar()
        await bd.cerrar()


def crear_app() -> FastAPI:
    app = FastAPI(title="buscaproducto", version="1.0", lifespan=ciclo_vida, docs_url=None, redoc_url=None)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.origenes_cors,
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
        allow_methods=["*"],
        allow_headers=["X-Clave", "Content-Type"],
        max_age=3600,
    )

    @app.get("/", response_class=PlainTextResponse)
    async def raiz() -> str:
        return "buscaproducto backend"

    # /holamundo y /salud los consume docs/holamundo.html desde Pages: CORS abierto y cuerpo exacto.
    @app.get("/holamundo")
    async def holamundo() -> PlainTextResponse:
        return PlainTextResponse("holamundo", headers={"Access-Control-Allow-Origin": "*"})

    @app.get("/salud")
    async def salud() -> JSONResponse:
        return JSONResponse(
            {"ok": True, "build": config.build_id}, headers={"Access-Control-Allow-Origin": "*"}
        )

    api = "/api/v1"
    app.include_router(herramientas.router, prefix=api)
    app.include_router(busquedas.router, prefix=api)
    app.include_router(sistema.router, prefix=api)
    for nombre in ("alertas", "ofertas", "informes", "tareas"):
        try:
            modulo = __import__(f"app.api.{nombre}", fromlist=["router"])
        except ImportError:
            continue
        app.include_router(modulo.router, prefix=api)

    @app.exception_handler(Exception)
    async def error_generico(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            {"error": "interno", "detalle": f"{type(exc).__name__}: {str(exc)[:300]}"}, status_code=500
        )

    return app


app = crear_app()
