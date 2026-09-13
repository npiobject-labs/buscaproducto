"""Nivel D: no consulta nada, devuelve un único resultado de tipo enlace con la plantilla rellena."""

from __future__ import annotations

from urllib.parse import quote_plus

from ..dominio import Consulta, OfertaCruda
from ..http import Politica
from . import AdaptadorBase, Contexto


def rellenar_plantilla(plantilla: str, texto: str) -> str:
    return plantilla.replace("{q}", quote_plus(texto))


class Adaptador(AdaptadorBase):
    slug = "enlace"
    nivel = "D"
    politica = Politica(ttl_cache_s=0, respetar_robots=False)

    async def buscar(self, consulta: Consulta, ctx: Contexto) -> list[OfertaCruda]:
        plantilla = ctx.herramienta.get("url_plantilla_busqueda")
        if not plantilla:
            return []
        return [
            OfertaCruda(
                url=rellenar_plantilla(plantilla, self.adaptar_consulta(consulta)),
                titulo=f"Buscar «{consulta.texto}» en {ctx.herramienta['nombre']}",
                tipo="enlace",
            )
        ]
