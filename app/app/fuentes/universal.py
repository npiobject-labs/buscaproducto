"""Nivel C: cualquier herramienta con url_plantilla_busqueda → página → markdown → Extractor (IA) → ofertas.

Con `necesita_js` (o si la página estática no da resultados) usa Firecrawl, si hay clave.
"""

from __future__ import annotations

from urllib.parse import quote_plus

from ..config import config
from ..dominio import Consulta, OfertaCruda
from ..http import Bloqueado, Politica, html_a_markdown
from . import AdaptadorBase, Contexto

URL_FIRECRAWL = "https://api.firecrawl.dev/v1/scrape"


class Adaptador(AdaptadorBase):
    slug = "universal"
    nivel = "C"
    politica = Politica(intervalo_s=2.0)

    def disponible(self, ctx: Contexto) -> tuple[bool, str]:
        if ctx.ia is None or not ctx.ia.disponible():
            return False, "sin_ia: el adaptador universal necesita el Extractor"
        return True, ""

    async def markdown(self, url: str, ctx: Contexto, necesita_js: bool) -> tuple[str, bool]:
        if not necesita_js:
            try:
                html, cache = await ctx.http.texto(
                    url,
                    politica=self.politica,
                    fuente=ctx.slug,
                    usar_cache=ctx.config.get("usar_cache", True),
                )
                md = html_a_markdown(html, url)
                if len(md) > 500:
                    return md, cache
            except Bloqueado:
                raise
            except Exception as e:  # noqa: BLE001 - probamos con Firecrawl
                ctx.config["error_estatico"] = f"{type(e).__name__}: {str(e)[:120]}"
        if not config.firecrawl_api_key:
            raise ValueError("la página necesita JavaScript y no hay FIRECRAWL_API_KEY")
        costes = getattr(ctx.ia, "costes", None)
        if costes is not None:
            ok, gastado, presupuesto = await costes.permitido("firecrawl")
            if not ok:
                raise ValueError(f"presupuesto de Firecrawl agotado ({gastado:.2f}/{presupuesto:.2f} €)")
        datos, cache = await ctx.http.json(
            URL_FIRECRAWL,
            metodo="POST",
            json_body={"url": url, "formats": ["markdown"], "onlyMainContent": True, "waitFor": 2500},
            cabeceras={
                "Authorization": f"Bearer {config.firecrawl_api_key}",
                "Content-Type": "application/json",
            },
            politica=Politica(intervalo_s=0.5, respetar_robots=False, timeout_s=60),
            fuente=ctx.slug,
            usar_cache=ctx.config.get("usar_cache", True),
        )
        if not cache and costes is not None:
            await costes.registrar("firecrawl", 1, detalle=url[:80])
        md = ((datos or {}).get("data") or {}).get("markdown") or ""
        if not md:
            raise ValueError("Firecrawl no devolvió contenido")
        return md[:60_000], cache

    async def buscar(self, consulta: Consulta, ctx: Contexto) -> list[OfertaCruda]:
        plantilla = ctx.herramienta.get("url_plantilla_busqueda")
        if not plantilla:
            return []
        url = plantilla.replace("{q}", quote_plus(self.adaptar_consulta(consulta)))
        md, cache = await self.markdown(url, ctx, bool(ctx.herramienta.get("necesita_js")))
        ctx.config["desde_cache"] = int(cache)
        ofertas = await ctx.ia.extraer_ofertas(md, url, ctx.herramienta["nombre"])
        return [o for o in ofertas if o.url and o.titulo and o.precio]
