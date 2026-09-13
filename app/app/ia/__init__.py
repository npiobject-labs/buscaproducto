"""Fachada de agentes IA: caché en `informes`, contador de costes, presupuesto y validación de salidas.

Todos los agentes usan el SDK oficial de Anthropic contra `config.ia_base_url` (gateway del proyecto).
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from ..bd import BD, a_json, ahora, de_json
from ..config import config
from ..costes import Costes
from ..dominio import ATRIBUTOS, Especificacion, Interpretacion, OfertaCruda
from ..http import Http
from . import prompts

BETA_FALLBACKS = "server-side-fallback-2026-07-01"


class _Atributos(BaseModel):
    id: int
    ram_gb: float | None = None
    almacenamiento_gb: float | None = None
    cpu: str | None = None
    gpu: str | None = None
    tdp_w: float | None = None
    pantalla_pulgadas: float | None = None
    resolucion: str | None = None
    peso_kg: float | None = None
    wifi: str | None = None
    ethernet_gbps: float | None = None
    sistema_operativo: str | None = None
    fanless: bool | None = None
    pantalla_mate: bool | None = None
    openwrt: bool | None = None
    formato: str | None = None
    marca: str | None = None
    modelo: str | None = None
    estado_producto: str | None = None


class _LoteAtributos(BaseModel):
    elementos: list[_Atributos]


class _OfertaExtraida(BaseModel):
    url: str
    titulo: str
    precio: float | None = None
    envio: float | None = None
    moneda: str = "EUR"
    estado_producto: str | None = None
    disponibilidad: str | None = None
    vendedor: str | None = None
    valoracion: float | None = None
    n_valoraciones: int | None = None
    imagen_url: str | None = None


class _ListaOfertas(BaseModel):
    ofertas: list[_OfertaExtraida]
    es_pagina_de_resultados: bool = True
    motivo: str = ""


class _Pareja(BaseModel):
    a: int
    b: int
    mismo_producto: bool
    confianza: float = Field(ge=0, le=1, default=0.5)


class _Duplicados(BaseModel):
    parejas: list[_Pareja]


class Cita(BaseModel):
    url: str
    cita: str = ""
    titulo: str = ""


class Informe(BaseModel):
    veredicto: str = "dudoso"  # apto | no_apto | dudoso
    confianza: float = Field(default=0.5, ge=0, le=1)
    resumen: str = ""
    motivos: list[str] = []
    consumo_w: float | None = None
    ruido: str | None = None
    citas: list[Cita] = []


class Comparacion(BaseModel):
    tabla: list[dict[str, Any]] = []
    pros_contras: dict[str, dict[str, list[str]]] = {}
    recomendacion: str = ""
    ganador_id: int | None = None


class Reparacion(BaseModel):
    diagnostico: str = ""
    selectores: dict[str, str] = {}
    codigo_propuesto: str = ""
    confianza: float = Field(default=0.3, ge=0, le=1)


class Agentes:
    def __init__(self, bd: BD, costes: Costes, http: Http, cliente: Any = None):
        self.bd, self.costes, self.http = bd, costes, http
        self._cliente = cliente
        self._agotado = False

    # ---------- infraestructura ----------
    @property
    def credenciales(self) -> bool:
        return bool(config.ia_token or config.anthropic_api_key)

    def disponible(self) -> bool:
        return (self._cliente is not None or self.credenciales) and not self._agotado

    @property
    def cliente(self) -> Any:
        if self._cliente is None:
            from anthropic import AsyncAnthropic

            kw: dict[str, Any] = {"base_url": config.ia_base_url, "max_retries": 2, "timeout": 120.0}
            if config.ia_token:
                kw["auth_token"] = config.ia_token
            else:
                kw["api_key"] = config.anthropic_api_key
            self._cliente = AsyncAnthropic(**kw)
        return self._cliente

    @staticmethod
    def _clave(*partes: Any) -> str:
        return hashlib.sha1(a_json(partes).encode()).hexdigest()

    async def _cacheado(self, tipo: str, clave: str) -> Any | None:
        fila = await self.bd.uno(
            "SELECT contenido_json, expira FROM informes WHERE tipo = ? AND clave = ?", (tipo, clave)
        )
        if fila and (not fila["expira"] or fila["expira"] > ahora()):
            return de_json(fila["contenido_json"])
        return None

    async def _guardar(
        self,
        tipo: str,
        clave: str,
        contenido: Any,
        modelo: str,
        uso: Any,
        ttl_dias: int | None,
        citas: Any = None,
    ) -> None:
        expira = (
            (datetime.now(UTC) + timedelta(days=ttl_dias)).isoformat(timespec="seconds") if ttl_dias else None
        )
        tin = int(getattr(uso, "input_tokens", 0) or 0) + int(getattr(uso, "cache_read_input_tokens", 0) or 0)
        tout = int(getattr(uso, "output_tokens", 0) or 0)
        await self.bd.ejecutar(
            "INSERT OR REPLACE INTO informes (tipo, clave, contenido_json, citas_json, modelo, tokens_in, tokens_out, creado, expira) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                tipo,
                clave,
                a_json(contenido),
                a_json(citas) if citas else None,
                modelo,
                tin,
                tout,
                ahora(),
                expira,
            ),
        )
        await self.costes.registrar_tokens(modelo, tin, tout, tipo)
        ok, _, _ = await self.costes.permitido("anthropic")
        self._agotado = not ok

    async def _comprobar_presupuesto(self) -> None:
        ok, gastado, presupuesto = await self.costes.permitido("anthropic")
        self._agotado = not ok
        if not ok:
            raise RuntimeError(f"presupuesto de IA agotado ({gastado:.2f}/{presupuesto:.2f} €)")

    def _extras(self) -> dict[str, Any]:
        if not config.ia_fallbacks:
            return {}
        return {"extra_headers": {"anthropic-beta": BETA_FALLBACKS}, "extra_body": {"fallbacks": "default"}}

    async def _parse(
        self,
        modelo: str,
        system: str,
        usuario: str,
        formato: type[BaseModel],
        effort: str = "medium",
        max_tokens: int = 8000,
        thinking: bool = True,
    ) -> tuple[BaseModel | None, Any]:
        """Llamada con salida estructurada; reintenta sin extras si el gateway rechaza los fallbacks."""
        kw: dict[str, Any] = {
            "model": modelo,
            "max_tokens": max_tokens,
            "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            "messages": [{"role": "user", "content": usuario}],
            "output_format": formato,
        }
        if thinking:
            kw["thinking"] = {"type": "adaptive"}
            kw["output_config"] = {"effort": effort}
        for extras in (self._extras(), {}):
            try:
                r = await self.cliente.messages.parse(**kw, **extras)
                break
            except Exception as e:  # noqa: BLE001
                if extras and _es_error_de_peticion(e):
                    continue
                raise
        if getattr(r, "stop_reason", "") == "refusal":
            await self.bd.evento(
                "la IA rechazó la petición", "ia", "aviso", detalle=str(getattr(r, "stop_details", ""))[:200]
            )
            return None, r.usage
        return r.parsed_output, r.usage

    # ---------- Intérprete ----------
    async def interpretar(self, texto: str) -> Interpretacion | None:
        clave = self._clave("interpretar", texto.strip().lower())
        cache = await self._cacheado("interpretacion", clave)
        if cache:
            return Interpretacion(**cache)
        await self._comprobar_presupuesto()
        salida, uso = await self._parse(
            config.modelo_principal,
            prompts.SISTEMA_INTERPRETE,
            prompts.usuario_interprete(texto),
            Interpretacion,
            effort="medium",
        )
        if salida is None:
            return None
        inter: Interpretacion = salida  # type: ignore[assignment]
        inter.especificaciones = [
            s for s in inter.especificaciones if s.clave in ATRIBUTOS or s.clave in ("fiable",)
        ]
        await self._guardar(
            "interpretacion", clave, inter.model_dump(), config.modelo_principal, uso, ttl_dias=90
        )
        await self.bd.ejecutar(
            "INSERT INTO ejemplos (texto, interpretacion_json, creado) VALUES (?,?,?)",
            (texto, a_json(inter.model_dump()), ahora()),
        )
        return inter

    # ---------- Extractor de atributos ----------
    async def extraer_atributos(
        self, elementos: list[tuple[int, str]], claves: list[str]
    ) -> dict[int, dict[str, Any]]:
        resultado: dict[int, dict[str, Any]] = {}
        pendientes = []
        for oid, titulo in elementos:
            cache = await self._cacheado("atributos", self._clave("atributos", titulo.lower()))
            if cache is not None:
                resultado[oid] = cache
            else:
                pendientes.append((oid, titulo))
        if not pendientes:
            return resultado
        await self._comprobar_presupuesto()
        for i in range(0, len(pendientes), 40):
            lote = pendientes[i : i + 40]
            usuario = prompts.usuario_extractor(lote, claves)
            salida, uso = await self._parse(
                config.modelo_rapido,
                prompts.SISTEMA_EXTRACTOR,
                usuario,
                _LoteAtributos,
                thinking=False,
                max_tokens=6000,
            )
            if salida is None:
                salida, uso = await self._parse(
                    config.modelo_reintento,
                    prompts.SISTEMA_EXTRACTOR,
                    usuario,
                    _LoteAtributos,
                    effort="low",
                    max_tokens=6000,
                )
            if salida is None:
                continue
            por_id = {e.id: e for e in salida.elementos}  # type: ignore[attr-defined]
            for oid, titulo in lote:
                e = por_id.get(oid)
                at = {
                    k: v
                    for k, v in (e.model_dump() if e else {}).items()
                    if k != "id" and v not in (None, "")
                }
                resultado[oid] = at
                await self.bd.ejecutar(
                    "INSERT OR REPLACE INTO informes (tipo, clave, contenido_json, modelo, creado) VALUES (?,?,?,?,?)",
                    (
                        "atributos",
                        self._clave("atributos", titulo.lower()),
                        a_json(at),
                        config.modelo_rapido,
                        ahora(),
                    ),
                    commit=False,
                )
            await self.bd.c.commit()
            await self.costes.registrar_tokens(
                config.modelo_rapido,
                int(getattr(uso, "input_tokens", 0) or 0),
                int(getattr(uso, "output_tokens", 0) or 0),
                "atributos",
            )
        return resultado

    # ---------- Extractor de páginas (adaptador universal) ----------
    async def extraer_ofertas(self, markdown: str, url: str, fuente: str) -> list[OfertaCruda]:
        clave = self._clave("ofertas", url, hashlib.sha1(markdown.encode()).hexdigest())
        cache = await self._cacheado("ofertas_pagina", clave)
        if cache is not None:
            return [OfertaCruda(**o) for o in cache]
        await self._comprobar_presupuesto()
        usuario = prompts.usuario_pagina(markdown, url, fuente)
        salida, uso = await self._parse(
            config.modelo_rapido,
            prompts.SISTEMA_PAGINA,
            usuario,
            _ListaOfertas,
            thinking=False,
            max_tokens=8000,
        )
        if salida is None or not salida.ofertas:  # type: ignore[attr-defined]
            salida, uso = await self._parse(
                config.modelo_reintento,
                prompts.SISTEMA_PAGINA,
                usuario,
                _ListaOfertas,
                effort="low",
                max_tokens=8000,
            )
        ofertas: list[OfertaCruda] = []
        if salida is not None:
            for o in salida.ofertas:  # type: ignore[attr-defined]
                d = o.model_dump()
                if d["url"].startswith("/"):
                    from urllib.parse import urljoin

                    d["url"] = urljoin(url, d["url"])
                if d["url"].startswith("http") and d["titulo"]:
                    ofertas.append(OfertaCruda(**d))
        await self._guardar(
            "ofertas_pagina", clave, [o.model_dump() for o in ofertas], config.modelo_rapido, uso, ttl_dias=1
        )
        return ofertas

    # ---------- Juez de duplicados ----------
    async def juzgar_duplicados(self, parejas: list[tuple[int, str, int, str]]) -> list[tuple[int, int]]:
        if not parejas:
            return []
        await self._comprobar_presupuesto()
        salida, uso = await self._parse(
            config.modelo_rapido,
            prompts.SISTEMA_DUPLICADOS,
            prompts.usuario_duplicados(parejas),
            _Duplicados,
            thinking=False,
            max_tokens=3000,
        )
        await self.costes.registrar_tokens(
            config.modelo_rapido,
            int(getattr(uso, "input_tokens", 0) or 0),
            int(getattr(uso, "output_tokens", 0) or 0),
            "duplicados",
        )
        if salida is None:
            return []
        return [(p.a, p.b) for p in salida.parejas if p.mismo_producto and p.confianza >= 0.7]  # type: ignore[attr-defined]

    # ---------- Investigador ----------
    async def investigar(
        self, producto: dict[str, Any], requisito: str, dominios: list[str], forzar: bool = False
    ) -> Informe | None:
        nombre = producto.get("nombre") or ""
        clave = self._clave("investigar", nombre.lower(), requisito)
        if not forzar:
            cache = await self._cacheado("investigacion", clave)
            if cache:
                return Informe(**cache)
        await self._comprobar_presupuesto()
        herramientas = [
            {
                "type": "web_search_20260209",
                "name": "web_search",
                "max_uses": 8,
                "allowed_domains": dominios[:64],
            },
            {
                "type": "web_fetch_20260209",
                "name": "web_fetch",
                "max_uses": 6,
                "allowed_domains": dominios[:64],
                "citations": {"enabled": True},
                "max_content_tokens": 20000,
            },
        ]
        kw: dict[str, Any] = {
            "model": config.modelo_principal,
            "max_tokens": 16000,
            "system": [
                {"type": "text", "text": prompts.SISTEMA_INVESTIGADOR, "cache_control": {"type": "ephemeral"}}
            ],
            "messages": [{"role": "user", "content": prompts.usuario_investigador(producto, requisito)}],
            "tools": herramientas,
            "thinking": {"type": "adaptive"},
            "output_config": {
                "effort": "medium",
                "format": {"type": "json_schema", "schema": _esquema(Informe)},
            },
        }
        r = None
        for extras in (self._extras(), {}):
            try:
                async with self.cliente.messages.stream(**kw, **extras) as flujo:
                    r = await flujo.get_final_message()
                break
            except Exception as e:  # noqa: BLE001
                if extras and _es_error_de_peticion(e):
                    continue
                raise
        for _ in range(3):
            if r is not None and r.stop_reason == "pause_turn":
                kw["messages"] = kw["messages"] + [{"role": "assistant", "content": r.content}]
                async with self.cliente.messages.stream(**kw) as flujo:
                    r = await flujo.get_final_message()
            else:
                break
        if r is None or r.stop_reason == "refusal":
            return None
        texto = next((b.text for b in r.content if getattr(b, "type", "") == "text"), "")
        citas = _citas_de(r)
        try:
            informe = Informe(**json.loads(texto))
        except (ValueError, TypeError):
            return None
        if citas and not informe.citas:
            informe.citas = [Cita(**c) for c in citas[:8]]
        await self._guardar(
            "investigacion",
            clave,
            informe.model_dump(),
            config.modelo_principal,
            r.usage,
            ttl_dias=30,
            citas=citas,
        )
        return informe

    # ---------- Comparador ----------
    async def comparar(self, productos: list[dict[str, Any]], criterios: str = "") -> Comparacion | None:
        clave = self._clave("comparar", sorted(p.get("id") or p.get("nombre") for p in productos), criterios)
        cache = await self._cacheado("comparacion", clave)
        if cache:
            return Comparacion(**cache)
        await self._comprobar_presupuesto()
        salida, uso = await self._parse(
            config.modelo_principal,
            prompts.SISTEMA_COMPARADOR,
            prompts.usuario_comparador(productos, criterios),
            Comparacion,
            effort="low",
            max_tokens=8000,
        )
        if salida is None:
            return None
        await self._guardar(
            "comparacion", clave, salida.model_dump(), config.modelo_principal, uso, ttl_dias=7
        )
        return salida  # type: ignore[return-value]

    # ---------- Reparador ----------
    async def reparar(self, slug: str, codigo: str, html: str, error: str) -> Reparacion | None:
        await self._comprobar_presupuesto()
        salida, uso = await self._parse(
            config.modelo_principal,
            prompts.SISTEMA_REPARADOR,
            prompts.usuario_reparador(slug, codigo, html, error),
            Reparacion,
            effort="high",
            max_tokens=16000,
        )
        await self.costes.registrar_tokens(
            config.modelo_principal,
            int(getattr(uso, "input_tokens", 0) or 0),
            int(getattr(uso, "output_tokens", 0) or 0),
            "reparacion",
        )
        return salida  # type: ignore[return-value]


def _esquema(modelo: type[BaseModel]) -> dict[str, Any]:
    esquema = modelo.model_json_schema()
    esquema["additionalProperties"] = False
    return esquema


def _citas_de(r: Any) -> list[dict[str, str]]:
    citas: list[dict[str, str]] = []
    vistas: set[str] = set()
    for b in getattr(r, "content", []) or []:
        for c in getattr(b, "citations", None) or []:
            url = getattr(c, "url", "") or ""
            if url and url not in vistas:
                vistas.add(url)
                citas.append(
                    {
                        "url": url,
                        "cita": (getattr(c, "cited_text", "") or "")[:300],
                        "titulo": getattr(c, "title", "") or "",
                    }
                )
        if getattr(b, "type", "") == "web_search_tool_result":
            contenido = getattr(b, "content", None)
            for res in contenido if isinstance(contenido, list) else []:
                url = getattr(res, "url", "") or ""
                if url and url not in vistas:
                    vistas.add(url)
                    citas.append({"url": url, "cita": "", "titulo": getattr(res, "title", "") or ""})
    return citas


def _es_error_de_peticion(e: Exception) -> bool:
    try:
        from anthropic import BadRequestError, NotFoundError

        return isinstance(e, BadRequestError | NotFoundError)
    except ImportError:
        return False


__all__ = ["Agentes", "Informe", "Comparacion", "Reparacion", "Cita", "Especificacion"]
