"""Corre en el runner de GitHub (no en el sandbox): robots.txt, enlaces de búsqueda y fixtures HTML reales."""

from __future__ import annotations

import json
import re
import ssl
import sys
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote_plus, urlsplit

RAIZ = Path(__file__).resolve().parents[1]
SEED = RAIZ / "app" / "app" / "seed" / "herramientas.json"
FIXTURES = RAIZ / "app" / "app" / "fuentes" / "fixtures"
UA = "buscaproducto/1.0 (+https://github.com/npiobject-labs/buscaproducto)"
CONSULTA = "mini pc 16gb"
ANTI_BOT = ("cf-chl", "challenge-platform", "captcha", "Just a moment", "Attention Required", "access denied", "datadome", "perimeterx", "_px")

# Fuentes de las que se guarda la página de resultados como fixture (nivel B/C).
FIXTURES_DE = {
    "geizhals": "https://geizhals.eu/?fs={q}",
    "idealo": "https://www.idealo.es/resultados.html?q={q}",
    "pccomponentes": "https://www.pccomponentes.com/buscar/?query={q}",
    "chollometro": "https://www.chollometro.com/search?q={q}",
    "chollometro-rss": "https://www.chollometro.com/rss/busqueda?q={q}",
    "kelkoo": "https://www.kelkoo.es/ss-{q}.html",
    "coolmod": "https://www.coolmod.com/busqueda/?q={q}",
    "mediamarkt": "https://www.mediamarkt.es/es/search.html?query={q}",
    "backmarket": "https://www.backmarket.es/es-es/search?q={q}",
    "geeknetic": "https://www.geeknetic.es/comparador-precios/buscar/{q}",
    "notebookcheck": "https://www.notebookcheck.org/Suche.99.0.html?q={q}",
}


def pedir(url: str, timeout: int = 25) -> tuple[int, str, bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "es-ES,es;q=0.9", "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"})
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            cuerpo = r.read(2_000_000)
            return r.status, r.headers.get("content-type", ""), cuerpo, r.geturl()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("content-type", "") if e.headers else "", e.read(200_000) if e.fp else b"", url
    except Exception as e:  # noqa: BLE001
        return 0, type(e).__name__, b"", url


def es_anti_bot(cuerpo: bytes) -> bool:
    t = cuerpo[:20000].decode("utf-8", "replace").lower()
    return any(s.lower() in t for s in ANTI_BOT)


def main() -> int:
    herramientas = json.loads(SEED.read_text(encoding="utf-8"))
    fecha = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    # 1) robots.txt por dominio
    dominios: dict[str, list[str]] = {}
    for h in herramientas:
        for u in (h.get("url"), h.get("url_plantilla_busqueda")):
            if u and u.startswith("http"):
                d = f"{urlsplit(u).scheme}://{urlsplit(u).netloc}"
                dominios.setdefault(d, []).append(h["slug"])
    filas = [f"# robots.txt de las fuentes\n\nGenerado por `fuentes.yml` el {fecha}. User-Agent: `{UA}`.\n", "| Dominio | Herramientas | Estado | Reglas relevantes (User-agent: * / buscaproducto) |", "|---|---|---|---|"]
    for d, slugs in sorted(dominios.items()):
        estado, _, cuerpo, _ = pedir(f"{d}/robots.txt", 15)
        texto = cuerpo.decode("utf-8", "replace") if estado == 200 else ""
        relevantes: list[str] = []
        bloque = False
        for linea in texto.splitlines()[:400]:
            l2 = linea.strip()
            if l2.lower().startswith("user-agent:"):
                agente = l2.split(":", 1)[1].strip().lower()
                bloque = agente in ("*", "buscaproducto")
            elif bloque and l2.lower().startswith(("disallow:", "allow:", "crawl-delay:")):
                relevantes.append(l2)
        resumen = "; ".join(relevantes[:12]) + (" …" if len(relevantes) > 12 else "")
        filas.append(f"| {d} | {', '.join(sorted(set(slugs)))} | {estado or 'error'} | {resumen.replace('|', '¦') or ('(sin robots.txt)' if estado == 404 else '(vacío)')} |")
    (RAIZ / "docs" / "planificacion" / "robots.md").write_text("\n".join(filas) + "\n", encoding="utf-8")
    # 2) enlaces de búsqueda
    filas = [f"# Verificación de las URL de búsqueda\n\nGenerado por `fuentes.yml` el {fecha}, con `{{q}}` = `{CONSULTA}`. Un 200 no garantiza resultados (puede haber anti-bot: columna «bot»).\n", "| slug | URL probada | Estado | bot | Tamaño | Redirigido a |", "|---|---|---|---|---|---|"]
    for h in herramientas:
        p = h.get("url_plantilla_busqueda")
        if not p:
            continue
        url = p.replace("{q}", quote_plus(CONSULTA))
        estado, _, cuerpo, final = pedir(url)
        filas.append(f"| `{h['slug']}` | {url} | {estado or 'error'} | {'sí' if es_anti_bot(cuerpo) else 'no'} | {len(cuerpo)} | {final if final != url else ''} |")
    (RAIZ / "docs" / "planificacion" / "enlaces.md").write_text("\n".join(filas) + "\n", encoding="utf-8")
    # 3) fixtures
    resultado = {}
    for slug, plantilla in FIXTURES_DE.items():
        url = plantilla.replace("{q}", quote_plus(CONSULTA))
        estado, tipo, cuerpo, final = pedir(url)
        bot = es_anti_bot(cuerpo)
        resultado[slug] = {"url": url, "estado": estado, "tipo": tipo, "bytes": len(cuerpo), "anti_bot": bot, "final": final, "fecha": fecha}
        if estado == 200 and cuerpo and not bot:
            carpeta = FIXTURES / slug.replace("-rss", "")
            carpeta.mkdir(parents=True, exist_ok=True)
            ext = "xml" if "rss" in slug or "xml" in tipo else "html"
            nombre = "busqueda-minipc-rss" if "rss" in slug else "busqueda-minipc"
            (carpeta / f"{nombre}.{ext}").write_bytes(cuerpo)
        print(f"{slug}: {estado} {len(cuerpo)} B anti_bot={bot}")
    FIXTURES.mkdir(parents=True, exist_ok=True)
    (FIXTURES / "_resultado.json").write_text(json.dumps(resultado, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
