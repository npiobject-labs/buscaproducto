"""Nivel B: Chollometro, página de búsqueda HTML. Cada tarjeta lleva sus datos en JSON (`data-vue3`).

robots.txt (fuentes.yml): `Allow: /` para la búsqueda. El RSS de búsqueda no existe (404), por eso se usa el HTML.
"""

from __future__ import annotations

import json
import re
from urllib.parse import quote_plus

from selectolax.parser import HTMLParser

from ..dominio import Consulta, OfertaCruda
from ..http import Politica
from . import AdaptadorBase, Contexto

URL = "https://www.chollometro.com/search?q={q}"
_PRECIO_TITULO = re.compile(r"(\d{1,4}(?:[.,]\d{1,2})?)\s*€")


class Adaptador(AdaptadorBase):
    slug = "chollometro"
    nivel = "B"
    politica = Politica(intervalo_s=2.0)

    async def buscar(self, consulta: Consulta, ctx: Contexto) -> list[OfertaCruda]:
        url = URL.replace("{q}", quote_plus(self.adaptar_consulta(consulta)))
        html, cache = await ctx.http.texto(
            url, politica=self.politica, fuente=self.slug, usar_cache=ctx.config.get("usar_cache", True)
        )
        ctx.config["desde_cache"] = int(cache)
        return parsear(html)


def _imagen(main: dict | None) -> str | None:
    if not main or not main.get("path") or not main.get("name"):
        return None
    # Formato del CDN observado en la web; si cambia, solo se pierde la miniatura.
    return f"https://static.chollometro.com/{main['path']}/{main['name']}/re/300x300/qt/70/{main['name']}.jpg"


def parsear(html: str) -> list[OfertaCruda]:
    arbol = HTMLParser(html)
    salida: list[OfertaCruda] = []
    for art in arbol.css("article.thread"):
        datos = None
        for nodo in art.css("div.js-vue3[data-vue3]"):
            try:
                d = json.loads(nodo.attributes.get("data-vue3") or "")
            except ValueError:
                continue
            if (
                isinstance(d, dict)
                and isinstance(d.get("props"), dict)
                and isinstance(d["props"].get("thread"), dict)
            ):
                datos = d["props"]["thread"]
                break
        enlace = art.css_first("a.thread-link, a[data-t='threadLink']")
        if datos is None:
            if enlace is None:
                continue
            titulo = enlace.text(strip=True)
            m = _PRECIO_TITULO.search(titulo)
            salida.append(
                OfertaCruda(
                    url=enlace.attributes.get("href") or "",
                    titulo=titulo,
                    precio=float(m.group(1).replace(",", ".")) if m else None,
                )
            )
            continue
        url = (
            enlace.attributes.get("href") if enlace is not None else None
        ) or f"https://www.chollometro.com/ofertas/{datos.get('titleSlug')}-{datos.get('threadId')}"
        envio = datos.get("shipping") or {}
        merchant = datos.get("merchant") or {}
        precio = datos.get("price")
        salida.append(
            OfertaCruda(
                url=url,
                titulo=datos.get("title") or (enlace.text(strip=True) if enlace is not None else ""),
                precio=float(precio) if isinstance(precio, int | float) and precio > 0 else None,
                envio=0.0
                if envio.get("isFree")
                else (
                    float(envio["price"])
                    if isinstance(envio.get("price"), int | float) and envio.get("price")
                    else None
                ),
                vendedor=merchant.get("merchantName"),
                n_valoraciones=datos.get("commentCount"),
                imagen_url=_imagen(datos.get("mainImage")),
                disponibilidad="expirado" if datos.get("isExpired") else "disponible",
                estado_producto="reacondicionado"
                if "reacond" in (datos.get("title") or "").lower()
                else None,
                texto_extra=f"temperatura {datos.get('temperature')}º · antes {datos.get('nextBestPrice')} €"
                if datos.get("nextBestPrice")
                else None,
                atributos={"temperatura": datos.get("temperature")}
                if datos.get("temperature") is not None
                else {},
            )
        )
    return [o for o in salida if o.url and o.titulo and o.disponibilidad != "expirado"]
