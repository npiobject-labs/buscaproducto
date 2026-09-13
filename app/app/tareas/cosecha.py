"""Cosechador: corre en el runner de GitHub Actions (cosechar.yml) con Playwright.

1. Pide al backend qué páginas necesitan navegador (fuentes con JS o degradadas) y qué ofertas vigiladas refrescar.
2. Las visita con Chromium respetando robots.txt, ritmo por dominio y User-Agent honesto; convierte a markdown.
3. Devuelve todo al backend (`POST /tareas/cosecha`), que extrae ofertas y precios con el Extractor (IA).
4. Refresca las fixtures de los adaptadores con parser; si el backend detecta «0 resultados anómalo», guarda la
   propuesta del Reparador para que el workflow abra una PR (nunca se fusiona sola).

Uso: BP_CLAVE=… BP_URL=https://<app>.fly.dev python -m app.tareas.cosecha
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import urllib.robotparser
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from ..config import RAIZ, config
from ..http import SENALES_ANTI_BOT, html_a_markdown

BASE = os.environ.get("BP_URL", "").rstrip("/")
CLAVE = os.environ.get("BP_CLAVE", "")
FIXTURES = RAIZ / "fuentes" / "fixtures"
INTERVALO_S = 2.5


class Navegador:
    def __init__(self) -> None:
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._ultimo: dict[str, float] = {}

    async def permitido(self, url: str) -> bool:
        p = urlsplit(url)
        base = f"{p.scheme}://{p.netloc}"
        if base not in self._robots:
            rp = urllib.robotparser.RobotFileParser()
            try:
                async with httpx.AsyncClient(headers={"User-Agent": config.user_agent}, timeout=15) as c:
                    r = await c.get(f"{base}/robots.txt")
                if r.status_code == 200:
                    rp.parse(r.text.splitlines())
                    self._robots[base] = rp
                else:
                    self._robots[base] = None
            except httpx.HTTPError:
                self._robots[base] = None
        rp = self._robots[base]
        return True if rp is None else rp.can_fetch(config.user_agent, url)

    async def esperar(self, url: str) -> None:
        d = urlsplit(url).netloc
        espera = self._ultimo.get(d, 0) + INTERVALO_S - time.time()
        if espera > 0:
            await asyncio.sleep(espera)
        self._ultimo[d] = time.time()

    async def visitar(self, page, url: str) -> tuple[str, str]:
        """(html, motivo). motivo vacío si fue bien."""
        if not await self.permitido(url):
            return "", "robots"
        await self.esperar(url)
        try:
            resp = await page.goto(url, wait_until="domcontentloaded", timeout=40_000)
            await page.wait_for_timeout(2500)
            html = await page.content()
        except Exception as e:  # noqa: BLE001
            return "", f"{type(e).__name__}: {str(e)[:120]}"
        if (
            resp is not None
            and resp.status in (403, 429, 503)
            or any(s.lower() in html[:20000].lower() for s in SENALES_ANTI_BOT)
        ):
            return "", f"anti_bot ({resp.status if resp else '?'})"
        return html, ""


async def main() -> int:
    if not (BASE and CLAVE):
        print("Faltan BP_URL o BP_CLAVE", file=sys.stderr)
        return 1
    from playwright.async_api import async_playwright

    cab = {"X-Clave": CLAVE}
    async with httpx.AsyncClient(headers=cab, timeout=120) as api:
        for intento in range(4):
            try:
                pendientes = (
                    (await api.get(f"{BASE}/api/v1/tareas/cosecha/pendientes")).raise_for_status().json()
                )
                break
            except httpx.HTTPError as e:
                print(f"backend no responde ({e}); reintento {intento + 1}/4")
                await asyncio.sleep(20)
        else:
            return 1
        print(
            f"pendientes: {len(pendientes['paginas'])} páginas, {len(pendientes['ofertas'])} ofertas, {len(pendientes['parsers'])} parsers"
        )
        nav = Navegador()
        salida: dict = {"paginas": [], "ofertas": [], "parsers": [], "omitidas": []}
        async with async_playwright() as pw:
            browser = await pw.chromium.launch()
            ctx = await browser.new_context(
                user_agent=config.user_agent, locale="es-ES", viewport={"width": 1280, "height": 900}
            )
            page = await ctx.new_page()
            for p in pendientes["paginas"][:25]:
                html, motivo = await nav.visitar(page, p["url"])
                if motivo:
                    salida["omitidas"].append({**p, "motivo": motivo})
                    continue
                salida["paginas"].append({**p, "markdown": html_a_markdown(html, p["url"])})
            for o in pendientes["ofertas"][:40]:
                html, motivo = await nav.visitar(page, o["url"])
                if motivo:
                    salida["omitidas"].append({**o, "motivo": motivo})
                    continue
                salida["ofertas"].append({**o, "markdown": html_a_markdown(html, o["url"], maximo=25_000)})
            for pr in pendientes["parsers"]:
                html, motivo = await nav.visitar(page, pr["url"])
                salida["parsers"].append({**pr, "html": html, "motivo": motivo})
                if html:
                    carpeta = FIXTURES / pr["slug"]
                    carpeta.mkdir(parents=True, exist_ok=True)
                    (carpeta / "busqueda-minipc.html").write_text(html, encoding="utf-8")
            await browser.close()
        r = (await api.post(f"{BASE}/api/v1/tareas/cosecha", json=salida)).raise_for_status().json()
    print(json.dumps({k: v for k, v in r.items() if k != "reparaciones"}, ensure_ascii=False))
    reparaciones = r.get("reparaciones") or []
    for rep in reparaciones:
        if rep.get("codigo_propuesto"):
            destino = RAIZ / "fuentes" / f"{rep['slug']}.py.propuesto"
            destino.write_text(rep["codigo_propuesto"], encoding="utf-8")
            print(
                f"propuesta del Reparador para {rep['slug']} en {destino} (confianza {rep.get('confianza')})"
            )
    resumen = Path(os.environ.get("GITHUB_STEP_SUMMARY", "/dev/null"))
    with resumen.open("a", encoding="utf-8") as f:
        f.write(
            f"### Cosecha\n\n- páginas: {len(salida['paginas'])} · ofertas: {len(salida['ofertas'])} · omitidas: {len(salida['omitidas'])}\n- resultado: `{json.dumps({k: v for k, v in r.items() if k != 'reparaciones'}, ensure_ascii=False)[:800]}`\n- reparaciones propuestas: {len(reparaciones)}\n"
        )
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as f:
            f.write(f"reparaciones={len(reparaciones)}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
