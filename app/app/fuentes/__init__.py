"""Registro de adaptadores: cada módulo de esta carpeta con una clase `Adaptador` se registra por su `slug`."""

from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from ..dominio import Consulta, Nivel, OfertaCruda
from ..http import Http, Politica

if TYPE_CHECKING:
    from ..bd import BD


@dataclass
class Contexto:
    bd: BD
    http: Http
    herramienta: dict[str, Any]
    ia: Any = None  # fachada de agentes (app.ia.Agentes); None en tests sin IA
    config: dict[str, Any] = field(default_factory=dict)

    @property
    def slug(self) -> str:
        return self.herramienta["slug"]


class FuenteAdapter(Protocol):
    slug: str
    nivel: Nivel
    politica: Politica

    def disponible(self, ctx: Contexto) -> tuple[bool, str]:
        """(True, '') si puede usarse; (False, motivo) si falta clave, etc."""
        ...

    def adaptar_consulta(self, consulta: Consulta) -> str: ...

    async def buscar(self, consulta: Consulta, ctx: Contexto) -> list[OfertaCruda]: ...


class AdaptadorBase:
    slug = "base"
    nivel: Nivel = "D"
    politica = Politica()

    def disponible(self, ctx: Contexto) -> tuple[bool, str]:
        return True, ""

    def adaptar_consulta(self, consulta: Consulta) -> str:
        return consulta.texto

    async def buscar(self, consulta: Consulta, ctx: Contexto) -> list[OfertaCruda]:  # pragma: no cover
        raise NotImplementedError


_REGISTRO: dict[str, AdaptadorBase] = {}


def registro() -> dict[str, AdaptadorBase]:
    if not _REGISTRO:
        for mod in pkgutil.iter_modules(__path__):
            if mod.name.startswith("_") or mod.name == "fixtures":
                continue
            modulo = importlib.import_module(f"{__name__}.{mod.name}")
            clase = getattr(modulo, "Adaptador", None)
            if clase is not None:
                inst = clase()
                _REGISTRO[inst.slug] = inst
    return _REGISTRO


def adaptador_para(herramienta: dict[str, Any]) -> AdaptadorBase | None:
    """Adaptador propio por slug; si no hay, `universal` (si hay plantilla y el universal existe) o `enlace`."""
    reg = registro()
    slug = herramienta.get("adaptador") or herramienta["slug"]
    if slug in reg:
        return reg[slug]
    if herramienta.get("url_plantilla_busqueda"):
        if "universal" in reg and herramienta.get("nivel") in ("C", "B", "A"):
            return reg["universal"]
        return reg.get("enlace")
    return None
