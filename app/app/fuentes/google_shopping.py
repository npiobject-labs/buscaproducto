"""Nivel A: Google Shopping a través de Serper.dev (/shopping). Nunca se scrapea a Google."""

from __future__ import annotations

from ..busqueda.normalizar import parsear_precio
from ..config import config
from ..dominio import Consulta, OfertaCruda
from ..http import Politica
from . import AdaptadorBase, Contexto

URL = "https://google.serper.dev/shopping"


class Adaptador(AdaptadorBase):
    slug = "google-shopping"
    nivel = "A"
    politica = Politica(intervalo_s=0.5, respetar_robots=False)

    def disponible(self, ctx: Contexto) -> tuple[bool, str]:
        if not config.serper_api_key:
            return False, "sin_clave: SERPER_API_KEY"
        return True, ""

    async def buscar(self, consulta: Consulta, ctx: Contexto) -> list[OfertaCruda]:
        costes = getattr(ctx.ia, "costes", None)
        if costes is not None:
            ok, gastado, presupuesto = await costes.permitido("serper")
            if not ok:
                raise ValueError(f"presupuesto de Serper agotado ({gastado:.2f}/{presupuesto:.2f} €)")
        texto = self.adaptar_consulta(consulta)
        cuerpo = {"q": texto, "gl": "es", "hl": "es", "num": 40}
        datos, cache = await ctx.http.json(
            URL,
            metodo="POST",
            json_body=cuerpo,
            cabeceras={"X-API-KEY": config.serper_api_key, "Content-Type": "application/json"},
            politica=self.politica,
            fuente=self.slug,
            usar_cache=ctx.config.get("usar_cache", True),
        )
        ctx.config["desde_cache"] = int(cache)
        if not cache and costes is not None:
            await costes.registrar("serper", 1, detalle=texto[:80])
        return parsear(datos, consulta)


def parsear(datos: dict, consulta: Consulta | None = None) -> list[OfertaCruda]:
    salida = []
    for it in datos.get("shopping") or []:
        precio = parsear_precio(it.get("price"))
        entrega = (it.get("delivery") or "").lower()
        envio = 0.0 if "gratis" in entrega or "free" in entrega else parsear_precio(it.get("delivery"))
        salida.append(
            OfertaCruda(
                url=it.get("link") or "",
                titulo=it.get("title") or "",
                precio=precio,
                envio=envio,
                vendedor=it.get("source"),
                valoracion=it.get("rating"),
                n_valoraciones=it.get("ratingCount"),
                imagen_url=it.get("imageUrl"),
                estado_producto="reacondicionado" if "reacond" in (it.get("title") or "").lower() else None,
                texto_extra=it.get("delivery"),
            )
        )
    return [o for o in salida if o.url and o.titulo]
