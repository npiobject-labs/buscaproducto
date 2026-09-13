"""Nivel A: eBay Browse API (item_summary/search) con OAuth client-credentials."""

from __future__ import annotations

import base64
import time

from ..config import config
from ..dominio import Consulta, OfertaCruda
from ..http import Politica
from . import AdaptadorBase, Contexto

URL_TOKEN = "https://api.ebay.com/identity/v1/oauth2/token"
URL_BUSQUEDA = "https://api.ebay.com/buy/browse/v1/item_summary/search"
CONDICIONES = {
    "nuevo": "NEW",
    "reacondicionado": "CERTIFIED_REFURBISHED|SELLER_REFURBISHED",
    "segunda_mano": "USED",
}


class Adaptador(AdaptadorBase):
    slug = "ebay"
    nivel = "A"
    politica = Politica(intervalo_s=0.5, respetar_robots=False)
    _token: tuple[str, float] = ("", 0.0)

    def disponible(self, ctx: Contexto) -> tuple[bool, str]:
        if not (config.ebay_client_id and config.ebay_client_secret):
            return False, "sin_clave: EBAY_CLIENT_ID / EBAY_CLIENT_SECRET"
        return True, ""

    async def _token_acceso(self, ctx: Contexto) -> str:
        token, caduca = Adaptador._token
        if token and caduca > time.time() + 60:
            return token
        credenciales = base64.b64encode(
            f"{config.ebay_client_id}:{config.ebay_client_secret}".encode()
        ).decode()
        datos, _ = await ctx.http.json(
            URL_TOKEN,
            metodo="POST",
            cabeceras={
                "Authorization": f"Basic {credenciales}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            datos={"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"},
            politica=Politica(ttl_cache_s=0, respetar_robots=False, intervalo_s=0),
            fuente=self.slug,
            usar_cache=False,
        )
        Adaptador._token = (datos["access_token"], time.time() + float(datos.get("expires_in", 7200)))
        return Adaptador._token[0]

    def filtro(self, c: Consulta) -> str:
        partes = ["deliveryCountry:ES", "priceCurrency:EUR"]
        if c.precio_min is not None or c.precio_max is not None:
            partes.append(f"price:[{c.precio_min or ''}..{c.precio_max or ''}]")
        if c.estado in CONDICIONES:
            partes.append(f"conditions:{{{CONDICIONES[c.estado]}}}")
        return ",".join(partes)

    async def buscar(self, consulta: Consulta, ctx: Contexto) -> list[OfertaCruda]:
        token = await self._token_acceso(ctx)
        from urllib.parse import urlencode

        url = (
            URL_BUSQUEDA
            + "?"
            + urlencode({"q": self.adaptar_consulta(consulta), "limit": 50, "filter": self.filtro(consulta)})
        )
        datos, cache = await ctx.http.json(
            url,
            cabeceras={
                "Authorization": f"Bearer {token}",
                "X-EBAY-C-MARKETPLACE-ID": "EBAY_ES",
                "Accept-Language": "es-ES",
            },
            politica=self.politica,
            fuente=self.slug,
            usar_cache=ctx.config.get("usar_cache", True),
        )
        ctx.config["desde_cache"] = int(cache)
        return parsear(datos)


def parsear(datos: dict) -> list[OfertaCruda]:
    salida = []
    for it in datos.get("itemSummaries") or []:
        precio = it.get("price") or {}
        envio = None
        for op in it.get("shippingOptions") or []:
            coste = (op.get("shippingCost") or {}).get("value")
            if coste is not None:
                envio = float(coste)
                break
        vendedor = it.get("seller") or {}
        try:
            valor = float(precio.get("value")) if precio.get("value") is not None else None
        except (TypeError, ValueError):
            valor = None
        salida.append(
            OfertaCruda(
                url=it.get("itemWebUrl") or it.get("itemHref") or "",
                titulo=it.get("title") or "",
                precio=valor,
                envio=envio,
                moneda=precio.get("currency") or "EUR",
                estado_producto=it.get("condition"),
                disponibilidad="disponible",
                vendedor=vendedor.get("username"),
                valoracion=(float(vendedor["feedbackPercentage"]) / 20)
                if vendedor.get("feedbackPercentage")
                else None,
                n_valoraciones=vendedor.get("feedbackScore"),
                imagen_url=(it.get("image") or {}).get("imageUrl"),
                texto_extra=" ".join(it.get("categories", [{}])[0].get("categoryName", "") for _ in [0])
                if it.get("categories")
                else None,
                ean=None,
                atributos={},
            )
        )
    return [o for o in salida if o.url and o.titulo]
