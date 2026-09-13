"""Cliente HTTP compartido: robots.txt vinculante, rate limit por dominio, caché, backoff y circuit breaker.

Todos los adaptadores pasan por aquí; ningún adaptador crea su propio cliente.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
import urllib.robotparser
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

import httpx

from .bd import BD, a_json, ahora, de_json
from .config import config

SENALES_ANTI_BOT = (
    "cf-chl",
    "challenge-platform",
    "captcha",
    "Attention Required",
    "Just a moment",
    "access denied",
)


class Bloqueado(Exception):
    """robots.txt prohíbe la URL, o la fuente responde con anti-bot, o el breaker está abierto."""


@dataclass
class Politica:
    intervalo_s: float = config.intervalo_dominio_s
    ttl_cache_s: int = config.ttl_cache_busqueda_s
    respetar_robots: bool = True
    timeout_s: float = config.timeout_fuente_s
    reintentos: int = 3


@dataclass
class _EstadoDominio:
    proxima_peticion: float = 0.0
    fallos: int = 0
    abierto_hasta: float = 0.0
    candado: asyncio.Lock = field(default_factory=asyncio.Lock)


class Http:
    def __init__(self, bd: BD):
        self.bd = bd
        self.cliente = httpx.AsyncClient(
            http2=True,
            follow_redirects=True,
            headers={"User-Agent": config.user_agent, "Accept-Language": "es-ES,es;q=0.9,en;q=0.5"},
            timeout=httpx.Timeout(config.timeout_fuente_s),
        )
        self.dominios: dict[str, _EstadoDominio] = {}
        self._robots: dict[str, tuple[urllib.robotparser.RobotFileParser | None, float]] = {}

    async def cerrar(self) -> None:
        await self.cliente.aclose()

    # ---------- caché ----------
    @staticmethod
    def clave_cache(metodo: str, url: str, cuerpo: str | None = None) -> str:
        return hashlib.sha1(f"{metodo} {url} {cuerpo or ''}".encode()).hexdigest()

    async def _de_cache(self, clave: str) -> dict[str, Any] | None:
        fila = await self.bd.uno("SELECT * FROM cache_http WHERE clave = ? AND expira > ?", (clave, ahora()))
        return fila

    async def _a_cache(
        self, clave: str, url: str, estado: int, cuerpo: bytes, cabeceras: dict, ttl: int
    ) -> None:
        expira = (datetime.now(UTC) + timedelta(seconds=ttl)).isoformat(timespec="seconds")
        await self.bd.ejecutar(
            "INSERT OR REPLACE INTO cache_http (clave, url, estado, cuerpo, cabeceras_json, obtenido, expira) VALUES (?,?,?,?,?,?,?)",
            (clave, url, estado, cuerpo, a_json(cabeceras), ahora(), expira),
        )

    # ---------- robots ----------
    async def permitido(self, url: str) -> bool:
        partes = urlsplit(url)
        base = f"{partes.scheme}://{partes.netloc}"
        rp, caducidad = self._robots.get(base, (None, 0.0))
        if caducidad < time.time():
            rp = urllib.robotparser.RobotFileParser()
            texto = await self._texto_robots(base)
            if texto is None:
                rp = None  # sin robots.txt (404 o error): permitido
            else:
                rp.parse(texto.splitlines())
            self._robots[base] = (rp, time.time() + config.ttl_cache_robots_s)
        if rp is None:
            return True
        return rp.can_fetch(config.user_agent, url)

    async def _texto_robots(self, base: str) -> str | None:
        url = f"{base}/robots.txt"
        clave = self.clave_cache("GET", url)
        cacheado = await self._de_cache(clave)
        if cacheado:
            return (
                None
                if cacheado["estado"] >= 400
                else bytes(cacheado["cuerpo"] or b"").decode("utf-8", "replace")
            )
        try:
            r = await self.cliente.get(url, timeout=10)
            await self._a_cache(clave, url, r.status_code, r.content[:200_000], {}, config.ttl_cache_robots_s)
            return r.text if r.status_code < 400 else None
        except httpx.HTTPError:
            return None

    # ---------- rate limit + breaker ----------
    def _estado(self, url: str) -> _EstadoDominio:
        dominio = urlsplit(url).netloc.lower()
        return self.dominios.setdefault(dominio, _EstadoDominio())

    async def _esperar_turno(self, url: str, politica: Politica) -> None:
        est = self._estado(url)
        if est.abierto_hasta > time.time():
            raise Bloqueado(f"circuit breaker abierto para {urlsplit(url).netloc}")
        async with est.candado:
            espera = est.proxima_peticion - time.time()
            if espera > 0:
                await asyncio.sleep(espera)
            est.proxima_peticion = time.time() + politica.intervalo_s

    async def _fallo(self, url: str, fuente: str | None, motivo: str) -> None:
        est = self._estado(url)
        est.fallos += 1
        if est.fallos >= config.fallos_breaker:
            est.abierto_hasta = time.time() + config.segundos_breaker
            est.fallos = 0
            await self.bd.evento(
                "circuit breaker abierto", fuente, "aviso", dominio=urlsplit(url).netloc, motivo=motivo
            )

    def _exito(self, url: str) -> None:
        self._estado(url).fallos = 0

    # ---------- petición ----------
    async def obtener(
        self,
        url: str,
        *,
        politica: Politica | None = None,
        fuente: str | None = None,
        metodo: str = "GET",
        cabeceras: dict[str, str] | None = None,
        json_body: Any = None,
        datos: Any = None,
        usar_cache: bool = True,
    ) -> tuple[bytes, dict[str, Any], bool]:
        """Devuelve (cuerpo, info, desde_cache). Lanza Bloqueado o httpx.HTTPError."""
        politica = politica or Politica()
        cuerpo_clave = a_json(json_body) if json_body is not None else (a_json(datos) if datos else None)
        clave = self.clave_cache(metodo, url, cuerpo_clave)
        if usar_cache and politica.ttl_cache_s > 0:
            cacheado = await self._de_cache(clave)
            if cacheado and cacheado["estado"] < 400:
                return (
                    bytes(cacheado["cuerpo"] or b""),
                    {"estado": cacheado["estado"], "cabeceras": de_json(cacheado["cabeceras_json"], {})},
                    True,
                )
        if politica.respetar_robots and metodo == "GET" and not await self.permitido(url):
            await self.bd.evento("robots.txt prohíbe la URL", fuente, "aviso", url=url)
            raise Bloqueado(f"robots.txt prohíbe {url}")
        ultimo_error: Exception | None = None
        for intento in range(politica.reintentos):
            await self._esperar_turno(url, politica)
            try:
                r = await self.cliente.request(
                    metodo, url, headers=cabeceras, json=json_body, data=datos, timeout=politica.timeout_s
                )
            except httpx.HTTPError as e:
                ultimo_error = e
                await self._fallo(url, fuente, type(e).__name__)
                await asyncio.sleep(2**intento)
                continue
            texto_inicio = r.text[:4000] if "text" in r.headers.get("content-type", "") else ""
            if r.status_code in (403, 503) and any(
                s.lower() in texto_inicio.lower() for s in SENALES_ANTI_BOT
            ):
                await self.bd.evento("respuesta anti-bot", fuente, "aviso", url=url, estado=r.status_code)
                await self._fallo(url, fuente, "anti_bot")
                raise Bloqueado(f"anti-bot en {urlsplit(url).netloc}")
            if r.status_code == 429 or r.status_code >= 500:
                ultimo_error = httpx.HTTPStatusError(f"HTTP {r.status_code}", request=r.request, response=r)
                await self._fallo(url, fuente, f"http_{r.status_code}")
                reintento = r.headers.get("retry-after")
                await asyncio.sleep(
                    min(float(reintento) if reintento and reintento.isdigit() else 2**intento, 30)
                )
                continue
            self._exito(url)
            info = {
                "estado": r.status_code,
                "cabeceras": {k: v for k, v in r.headers.items() if k.lower() in ("content-type", "etag")},
            }
            if r.status_code < 400 and usar_cache and politica.ttl_cache_s > 0:
                await self._a_cache(
                    clave, url, r.status_code, r.content, info["cabeceras"], politica.ttl_cache_s
                )
            if r.status_code >= 400:
                raise httpx.HTTPStatusError(f"HTTP {r.status_code}", request=r.request, response=r)
            return r.content, info, False
        assert ultimo_error is not None
        raise ultimo_error

    async def texto(self, url: str, **kw: Any) -> tuple[str, bool]:
        cuerpo, _, cache = await self.obtener(url, **kw)
        return cuerpo.decode("utf-8", "replace"), cache

    async def json(self, url: str, **kw: Any) -> tuple[Any, bool]:
        import json as _json

        cuerpo, _, cache = await self.obtener(url, **kw)
        return _json.loads(cuerpo or b"null"), cache
