# Catálogo de herramientas de búsqueda

> Catálogo vivo y **ampliable a mano**: ver [Cómo añadir una herramienta a mano](#cómo-añadir-una-herramienta-a-mano). Alimenta el mock (F1) y el seed de la tabla `herramientas` (`app/seed/herramientas.json`, F2), que se genera a partir de este fichero con `python -m app.seed.generar`.
>
> Hereda el catálogo del proyecto local y lo amplía con `url_plantilla_busqueda`, `nivel` de integración y una categoría 7 de infraestructura propia. Las plantillas marcadas **(verificar)** son **[SUPUESTO]**: las confirma `verificar-enlaces.yml` en F2.3 y se corrigen aquí.

**Leyenda**

- `tipo_acceso`: `web` | `api` | `extensión` | `ia` | `comunidad` | `librería` | `self-hosted` | `rss`
- `nivel` (ver [PLAN.md §7](PLAN.md#7-estrategia-de-fuentes)): **A** API · **B** scraping propio · **C** adaptador universal IA · **D** enlace manual · `—` no participa en búsquedas (herramienta de apoyo)
- `politica_scraping`: `api oficial` | `verificar robots` | `hostil (usar API)` | `n/a`
- `fase`: cuándo se integra al nivel indicado

## 1. Comparadores de precios

| slug | Nombre | URL | url_plantilla_busqueda | tipo | Coste | nivel | fase | politica | Notas |
|---|---|---|---|---|---|---|---|---|---|
| `idealo` | Idealo | https://www.idealo.es | `https://www.idealo.es/resultados.html?q={q}` | web | gratis | C | F4 | verificar robots | Líder ES/EU. `fuentes.yml` 2026-09-13: 403 a peticiones directas → nivel C (Firecrawl) o D |
| `google-shopping` | Google Shopping | https://shopping.google.es | `https://www.google.es/search?tbm=shop&q={q}` | web / api | gratis (Serper de pago) | A (Serper) | F3 | hostil (usar API) | Mayor cobertura; rango de precios |
| `geizhals` | Geizhals / Skinflint | https://geizhals.eu | `https://geizhals.eu/?fs={q}` | web | gratis | C | F4 | verificar robots | Filtros técnicos finísimos. `fuentes.yml`: 403 anti-bot a peticiones directas → nivel C (Firecrawl) o D |
| `kelkoo` | Kelkoo | https://www.kelkoo.es | `https://www.kelkoo.es/ss-{q}.html` (verificar) | web | gratis | C | F4 | verificar robots | Electrónica, informática |
| `geeknetic` | Geeknetic Comparador | https://www.geeknetic.es/comparador-precios | `https://www.geeknetic.es/comparador-precios/buscar/{q}` (verificar) | web | gratis | C | F4 | verificar robots | Hardware, mercado ES. `fuentes.yml`: la URL redirige a la portada; plantilla pendiente de corregir |

## 2. Tiendas con buen buscador

| slug | Nombre | URL | url_plantilla_busqueda | tipo | Coste | nivel | fase | politica | Notas |
|---|---|---|---|---|---|---|---|---|---|
| `amazon-es` | Amazon.es | https://www.amazon.es | `https://www.amazon.es/s?k={q}` | web | gratis | D → A (Keepa) | F2 / F8 | hostil (usar API) | Nunca scraping directo; Keepa opcional por coste |
| `pccomponentes` | PcComponentes | https://www.pccomponentes.com | `https://www.pccomponentes.com/buscar/?query={q}` | web | gratis | C (Firecrawl) | F4 | verificar robots | Referencia de hardware ES. `fuentes.yml`: 403 anti-bot confirmado → solo Firecrawl o D |
| `coolmod` | Coolmod | https://www.coolmod.com | `https://www.coolmod.com/busqueda/?q={q}` (verificar) | web | gratis | C | F4 | verificar robots | Hardware y gaming ES |
| `ebay` | eBay | https://www.ebay.es | `https://www.ebay.es/sch/i.html?_nkw={q}` | web / api | gratis | A (Browse API) | F3 | api oficial | Nuevo y segunda mano; filtros de estado y precio |
| `aliexpress` | AliExpress | https://es.aliexpress.com | `https://es.aliexpress.com/wholesale?SearchText={q}` | web / api | gratis | D | F2 | hostil (usar API) | Plazos largos, aduanas; Affiliate API solo si compensa |
| `mediamarkt` | MediaMarkt | https://www.mediamarkt.es | `https://www.mediamarkt.es/es/search.html?query={q}` | web | gratis | C | F4 | verificar robots | Recogida en tienda |
| `backmarket` | Back Market | https://www.backmarket.es | `https://www.backmarket.es/es-es/search?q={q}` | web | gratis | C | F4 | verificar robots | Reacondicionado con garantía |
| `wallapop` | Wallapop | https://es.wallapop.com | `https://es.wallapop.com/app/search?keywords={q}` | web / app | gratis | D | F2 | hostil | Segunda mano local |

## 3. Histórico y alertas de precio

| slug | Nombre | URL | url_plantilla_busqueda | tipo | Coste | nivel | fase | politica | Notas |
|---|---|---|---|---|---|---|---|---|---|
| `keepa` | Keepa | https://keepa.com | — | extensión / api | API de pago | A | F8 | api oficial | Histórico de Amazon; opcional (≈ 19 €/mes) |
| `camelcamelcamel` | CamelCamelCamel | https://es.camelcamelcamel.com | `https://es.camelcamelcamel.com/search?sq={q}` | web / extensión | gratis | D | F2 | n/a | Histórico Amazon + alertas email |
| `chollometro` | Chollometro | https://www.chollometro.com | `https://www.chollometro.com/search?q={q}` | web | gratis | B | F3 | verificar robots | Comunidad de ofertas ES. Adaptador `chollometro` (HTML, datos en `data-vue3`); robots `Allow: /`. El RSS de búsqueda no existe (404) |
| `changedetection` | changedetection.io | https://changedetection.io | — | self-hosted | OSS | — | — | n/a | Sustituido por el cosechador propio; queda como referencia |

## 4. Asistentes IA de compra

Participan solo como **enlace** (abren la consulta en el asistente); la IA propia de la app está en la categoría 7.

| slug | Nombre | URL | url_plantilla_busqueda | tipo | Coste | nivel | fase | politica | Notas |
|---|---|---|---|---|---|---|---|---|---|
| `perplexity` | Perplexity Shopping | https://www.perplexity.ai | `https://www.perplexity.ai/search?q={q}` | ia | freemium | D | F2 | n/a | Comparación con fuentes citadas |
| `chatgpt` | ChatGPT | https://chatgpt.com | `https://chatgpt.com/?q={q}` | ia | freemium | D | F2 | n/a | Descubrimiento de producto |
| `gemini` | Google Gemini / AI Mode | https://gemini.google.com | `https://www.google.es/search?udm=50&q={q}` (verificar) | ia | freemium | D | F2 | n/a | Integrado con Google Shopping |
| `rufus` | Amazon Rufus | https://www.amazon.es | — | ia | gratis | — | — | n/a | Solo dentro de Amazon |
| `claude` | Claude | https://claude.ai | `https://claude.ai/new?q={q}` | ia | freemium | D | F2 | n/a | Razonamiento sobre especificaciones |
| `copilot` | Microsoft Copilot | https://copilot.microsoft.com | `https://copilot.microsoft.com/?q={q}` | ia | freemium | D | F2 | n/a | |

## 5. APIs y servicios de scraping

| slug | Nombre | URL | tipo | Coste | Uso en la app | fase | Notas |
|---|---|---|---|---|---|---|---|
| `serper` | Serper.dev | https://serper.dev | api | 2.500 créditos gratis; ≈ 1 $/1.000 | Adaptador `google-shopping` (nivel A) | F3 | Elegido sobre SerpAPI por precio |
| `serpapi` | SerpAPI | https://serpapi.com | api | 75 $/5.000 | Alternativa a Serper | — | Solo si Serper falla |
| `ebay-browse` | eBay Browse API | https://developer.ebay.com | api | gratis | Adaptador `ebay` | F3 | OAuth client-credentials |
| `firecrawl` | Firecrawl | https://firecrawl.dev | api | 500 créditos gratis | Motor del adaptador universal cuando la página necesita JS | F4 | HTML → markdown limpio |
| `apify` | Apify | https://apify.com | api / saas | crédito gratis mensual | Actores para fuentes que fallen en C | F8 | |
| `keepa-api` | Keepa API | https://keepa.com/#!api | api | pago | Adaptador `keepa` | F8 | Opcional |
| `reddit-api` | Reddit API | https://www.reddit.com/dev/api | api | gratis (OAuth) | Investigador | F6 | 100 req/min |
| `httpx-selectolax` | httpx + selectolax | https://www.python-httpx.org | librería | OSS | Nivel B en vivo | F3 | HTML estático |
| `playwright` | Playwright (Python) | https://playwright.dev/python | librería | OSS | Solo en `cosechar.yml` (runner) | F8 | No va en la imagen de Fly |
| `crawl4ai` | crawl4ai | https://github.com/unclecode/crawl4ai | librería | OSS | Conversión HTML → markdown en el cosechador | F8 | Alternativa a Firecrawl sin coste |
| `scrapy` | Scrapy | https://scrapy.org | librería | OSS | No previsto | — | Sobredimensionado para este uso |
| `scraperapi` | ScraperAPI / Zyte | https://scraperapi.com | api | pago | No previsto | — | Proxies gestionados: fuera de alcance |

## 6. Comunidades y reviews (requisitos blandos)

Dominios permitidos del Investigador (`allowed_domains`).

| slug | Nombre | URL | url_plantilla_busqueda | tipo | nivel | fase | Notas |
|---|---|---|---|---|---|---|---|
| `r-minipcs` | Reddit r/MiniPCs | https://www.reddit.com/r/MiniPCs | `https://www.reddit.com/r/MiniPCs/search?q={q}&restrict_sr=1` | comunidad | D + Investigador | F2 / F6 | Experiencias por modelo |
| `r-homeserver` | Reddit r/HomeServer · r/selfhosted | https://www.reddit.com/r/HomeServer | `https://www.reddit.com/r/HomeServer/search?q={q}&restrict_sr=1` | comunidad | D + Investigador | F2 / F6 | Uso 24/7, consumo |
| `servethehome` | ServeTheHome | https://www.servethehome.com | `https://www.servethehome.com/?s={q}` | web | D + Investigador | F2 / F6 | Proyecto TinyMiniMicro |
| `liliputing` | Liliputing | https://liliputing.com | `https://liliputing.com/?s={q}` | web | D + Investigador | F2 / F6 | Fichas de MiniPCs |
| `notebookcheck` | NotebookCheck | https://www.notebookcheck.org | `https://www.notebookcheck.org/Suche.99.0.html?q={q}` (verificar) | web | D + Investigador | F2 / F6 | Consumo y temperaturas |
| `forocoches` | Forocoches Hard-Soft · Mediavida | https://forocoches.com | `https://www.mediavida.com/buscar?q={q}` (verificar) | comunidad | D + Investigador | F2 / F6 | Hilos de compra ES |
| `youtube` | YouTube (reviews) | https://www.youtube.com | `https://www.youtube.com/results?search_query={q}+review` | web | D | F2 | Solo enlace |

## 7. Infraestructura propia (IA, notificaciones, ejecución)

No aparecen como fuentes en la pestaña Búsqueda; sí en el catálogo (pestaña Herramientas) con su estado (clave presente, consumo del mes).

| slug | Nombre | URL | tipo | Coste | Uso | fase |
|---|---|---|---|---|---|---|
| `anthropic` | Claude API (Opus 5, Sonnet 5, Haiku 4.5) | https://docs.claude.com | api | por token | Intérprete, Extractor, Investigador, Comparador, Reparador | F4 |
| `telegram` | Telegram Bot API | https://core.telegram.org/bots/api | api | gratis | Alertas | F5 |
| `fly` | Fly.io | https://fly.io | saas | 2–4 €/mes | Backend + volumen SQLite | F2 |
| `github-actions` | GitHub Actions | https://github.com/features/actions | saas | gratis (público) | Crons, cosechador con Playwright, verificaciones, copias | F5 / F8 |
| `github-pages` | GitHub Pages | https://pages.github.com | saas | gratis | Frontend PWA | F1 |

**Total: 47 herramientas** en 7 categorías (42 en las 6 de búsqueda; 28 participan en las búsquedas). Objetivo C2 del plan: ≥ 12 devolviendo ofertas reales al cierre.

Resultado real de `fuentes.yml` (2026-09-13, petición directa educada desde el runner): responden 200 Chollometro, ServeTheHome, YouTube y Geeknetic (portada); devuelven **403 anti-bot** Geizhals, PcComponentes, Kelkoo, Coolmod, MediaMarkt y Liliputing; 403 sin página de bloqueo Idealo, Back Market y Reddit; 404 NotebookCheck (URL errónea). Detalle en [enlaces.md](enlaces.md) y [robots.md](robots.md). Consecuencia: esas fuentes trabajan en nivel C (Firecrawl, si hay clave) o D; nunca se intenta evadir el bloqueo.

---

## Cómo añadir una herramienta a mano

Cualquier web se incorpora **sin código** rellenando estos campos (los mismos en este documento, en el mock y en la tabla `herramientas`):

| Campo | Obligatorio | Descripción |
|---|---|---|
| `nombre` | ✔ | Nombre visible |
| `categoria` | ✔ | Una de las 7 (u «Otra») |
| `url` | ✔ | URL principal |
| `url_plantilla_busqueda` | — | URL de búsqueda con `{q}`. **Con ella, la herramienta empieza en nivel D y sube sola a C** en cuanto el adaptador universal extrae ≥ 1 oferta válida |
| `tipo_acceso` | — | web / api / extensión / ia / comunidad / rss |
| `coste` | — | gratis / freemium / pago / open source |
| `descripcion` | — | Para qué sirve |
| `activa` | — | Participa en las búsquedas (sí por defecto) |
| `necesita_js` | — | Fuerza Firecrawl en vez de httpx en el nivel C |

- **Mock (F1):** pestaña Herramientas → «+ Añadir herramienta» → `localStorage`, badge «Añadida por ti».
- **Web real (F2+):** mismo formulario → `POST /api/v1/herramientas`; botón «Probar» → `POST /herramientas/{id}/probar` muestra el nivel alcanzado y una oferta de ejemplo.
- **Este documento:** añadir una fila en su categoría; el `slug` se deriva del nombre. `python -m app.seed.generar` regenera el seed y `ci.yml` falla si el seed y el catálogo divergen.
- **Con código (nivel B o A):** un fichero en `app/fuentes/<slug>.py` + fixture + test; `herramientas.adaptador = slug`.

### Plantilla de fila vacía

```markdown
| `mi-slug` | Mi herramienta | https://… | `https://…?q={q}` | web | gratis | D | — | verificar robots | … |
```
