# BuscaProducto — Arquitectura

> Diseño técnico de las fases F2–F8 del [PLAN.md](PLAN.md). Decisiones justificadas en [DECISIONES.md](DECISIONES.md).

## Índice

1. [Vista general](#1-vista-general)
2. [Frontend (Pages)](#2-frontend-pages)
3. [Backend (Fly)](#3-backend-fly)
4. [Modelo de datos](#4-modelo-de-datos)
5. [Fuentes: adaptadores y pipeline de búsqueda](#5-fuentes-adaptadores-y-pipeline-de-búsqueda)
6. [IA y agentes](#6-ia-y-agentes)
7. [Anti-bloqueo respetuoso](#7-anti-bloqueo-respetuoso)
8. [Tareas programadas: vigilar y cosechar](#8-tareas-programadas-vigilar-y-cosechar)
9. [Seguridad y secretos](#9-seguridad-y-secretos)
10. [Despliegue y verificación](#10-despliegue-y-verificación)
11. [Tests](#11-tests)
12. [Estructura de carpetas](#12-estructura-de-carpetas)

---

## 1. Vista general

```
 móvil / navegador
       │  HTTPS
       ▼
 GitHub Pages ── docs/index.html (PWA estática, sin claves)
       │  fetch /api/v1/*  +  X-Clave   (CORS)
       ▼
 Fly.io ── app/ (Python 3.12 · FastAPI · uvicorn) ── SQLite en volumen /datos
       │                 │                    │
       │                 │                    └── Anthropic API (Intérprete, Extractor, Investigador)
       │                 └── Adaptadores: eBay · Serper · Keepa · Firecrawl · httpx+selectolax · RSS
       ▲
 GitHub Actions ── vigilar.yml (cron diario) · cosechar.yml (Playwright en runner) · deploy.yml · ci.yml
                                                           │
                                                           └── Telegram Bot API (alertas)
```

- **Un solo servicio** en Fly con una máquina que se apaga sola. El cron de Actions la despierta.
- **Todo lo pesado o programado** corre en GitHub Actions (gratuito en repo público): Playwright, cosecha nocturna, verificación de robots y enlaces, copias de seguridad.
- **La IA es un componente más**, detrás de una interfaz `Agente` con caché y presupuesto, nunca en el camino crítico si hay caché.

## 2. Frontend (Pages)

- `docs/index.html`: un único fichero (HTML + CSS + JS vainilla), sin CDNs. Evoluciona del mock: la misma pantalla funciona en **modo demo** (datos embebidos, `file://`) y en **modo real** (cuando hay clave guardada).
- Descubre el backend como `docs/holamundo.html`: `<meta name="fly-app">` → `https://<app>.fly.dev`; en `localhost` usa `?api=` (8080 por defecto).
- Clave: la pide una vez, la guarda en `localStorage` (`bp.clave`), la envía en la cabecera `X-Clave`. Sin clave → modo demo con aviso.
- Estado de búsqueda: `POST /busquedas` → `id` → polling de `GET /busquedas/{id}` cada 1,5 s hasta `estado ∈ {terminada, error}`; los resultados se van pintando según llegan (`GET /busquedas/{id}/resultados?desde=<n>`).
- URL compartible: `#b=<id>` reabre una búsqueda; `#q=<texto>&min=&max=&spec=ram>=8` lanza una nueva.
- PWA (F7): `docs/manifest.webmanifest` + `docs/sw.js` (caché solo de estáticos, nunca de `/api`).
- Gráfico de histórico: SVG generado en JS, sin librerías.
- Accesibilidad: pestañas `role=tablist`, modal con foco atrapado, contraste AA, `prefers-color-scheme`.

## 3. Backend (Fly)

- **Python 3.12**, FastAPI + uvicorn, `httpx` (HTTP/2, async), `selectolax` (HTML), `feedparser` (RSS), `rapidfuzz` (dedupe), `pydantic` v2, `sqlite3` estándar con `aiosqlite`, `anthropic` (SDK oficial), `tenacity`.
- Gestión de dependencias con `uv` (`pyproject.toml` + `uv.lock`); Dockerfile multi-etapa sobre `python:3.12-slim`; **sin Playwright en la imagen** (ver §8).
- Contratos que hereda de la plantilla y **no cambian**: `GET /` texto plano, `GET /salud` → `{"ok":true,"build":"<BUILD_ID>"}`, `GET /holamundo` → `holamundo`, CORS `*` en ambas, puerto 8080, `PUERTO` solo para el PC.
- Nuevo: `/api/v1/*` con `CORSMiddleware` (`allow_origins=["https://npiobject-labs.github.io", "http://localhost:8081"]`, `allow_headers=["X-Clave","Content-Type"]`) y dependencia `requiere_clave`.
- Tareas asíncronas dentro del proceso (`asyncio.create_task` + tabla `busquedas` como estado). Si la máquina se apaga a mitad, la búsqueda queda `interrumpida` y el frontend ofrece relanzar. **[SUPUESTO]** suficiente para un usuario; plan B: cola en SQLite procesada por un segundo proceso `worker` en la misma máquina.
- Configuración por variables de entorno (`BP_*`), todas con valor por defecto salvo `BP_CLAVE`.

### API `/api/v1`

| Método y ruta | Qué hace |
|---|---|
| `GET /herramientas` · `POST` · `PUT /{id}` · `DELETE /{id}` · `PATCH /{id}/activa` | Catálogo; las predefinidas solo se activan/desactivan |
| `POST /herramientas/{id}/probar` | Lanza una búsqueda de prueba solo en esa fuente y devuelve nivel alcanzado |
| `POST /busquedas` | Cuerpo: `{texto?, especificaciones?, precio_min?, precio_max?, fuentes?, interpretar: bool}` → `{id, interpretacion?}` |
| `GET /busquedas/{id}` | Estado, progreso por fuente, interpretación, facetas |
| `GET /busquedas/{id}/resultados?desde=&orden=&filtros…` | Ofertas agrupadas por producto, paginadas |
| `GET /busquedas?limite=` | Historial de búsquedas |
| `POST /interpretar` | Solo el Intérprete: texto → especificaciones (para «lo que he entendido» antes de buscar) |
| `GET /ofertas/{id}/historico` | Serie de precios + mínimo, mediana, veredicto |
| `GET /productos/{id}/informe?requisito=24x7` · `POST …/informe` | Informe del Investigador (caché o generación) |
| `POST /comparar` | `{producto_ids:[…]}` → tabla lado a lado + pros/contras |
| `GET /alertas` · `POST` · `DELETE /{id}` | Alertas |
| `POST /tareas/vigilar` | Cron: refresca ofertas vigiladas, evalúa alertas, envía Telegram |
| `POST /tareas/cosecha` | Recibe ofertas del cosechador de Actions |
| `GET /eventos?desde=` | Bitácora del backend (robots, rate limit, circuit breaker, costes) |
| `GET /costes` | Consumo por proveedor en el mes |
| `GET /exportar/{busqueda_id}.csv` | CSV |

Errores: JSON `{error, detalle}`; 401 sin clave; 429 si el presupuesto de un proveedor está agotado (se degrada a fuentes sin coste).

## 4. Modelo de datos

SQLite, `PRAGMA journal_mode=WAL`, migraciones numeradas en `app/migraciones/NNN.sql` aplicadas al arrancar.

| Tabla | Campos clave | Notas |
|---|---|---|
| `herramientas` | `id, slug, nombre, categoria, url, url_plantilla_busqueda, tipo_acceso, coste, descripcion, origen(predefinida\|usuario), activa, nivel(A\|B\|C\|D), adaptador, politica_scraping, config_json, creada, actualizada` | Seed desde `app/seed/herramientas.json`, generado a partir de CATALOGO_HERRAMIENTAS.md |
| `busquedas` | `id, texto, especificaciones_json, precio_min, precio_max, fuentes_json, estado, interpretacion_json, facetas_json, creada, terminada` | `estado ∈ pendiente, en_curso, terminada, interrumpida, error` |
| `busqueda_fuentes` | `busqueda_id, herramienta_id, estado, n_ofertas, error, ms, desde_cache, nivel_usado` | Progreso por fuente |
| `productos` | `id, clave_canonica, nombre, marca, modelo, categoria, atributos_json, imagen_url, actualizado` | Agrupa ofertas; clave = EAN/ASIN si existe, si no marca+modelo normalizados |
| `ofertas` | `id, producto_id, herramienta_id, url, titulo, precio, envio, moneda, estado_producto, disponibilidad, vendedor, valoracion, n_valoraciones, imagen_url, atributos_json, hash, primera_vez, ultima_vez, vigilada` | `hash` = sha1(herramienta, url normalizada) |
| `busqueda_ofertas` | `busqueda_id, oferta_id, puntuacion, explicacion_json, posicion` | Puntuación es relativa a la búsqueda |
| `precios` | `oferta_id, fecha, precio, envio` | Histórico; una fila por cambio, no por consulta |
| `alertas` | `id, tipo(precio_objetivo\|nueva_oferta), busqueda_id, oferta_id, umbral, canal, activa, ultima_comprobacion, ultimo_disparo` | |
| `cache_http` | `clave, url, estado, cuerpo, cabeceras_json, obtenido, expira` | TTL 6 h para búsquedas, 24 h para robots |
| `informes` | `id, tipo(interpretacion\|atributos\|investigacion\|comparacion\|reparacion), clave, contenido_json, citas_json, modelo, tokens_in, tokens_out, creado, expira` | Caché de todo lo que produce la IA |
| `costes_api` | `fecha, proveedor, unidades, coste_estimado` | Presupuesto (RF-21) |
| `eventos` | `id, fecha, nivel, fuente, mensaje, datos_json` | Robots, rate limit, circuit breaker, 0 anómalo |
| `ejemplos` | `id, texto, interpretacion_json, correccion_json, creado` | Correcciones del usuario → evaluación del Intérprete |

## 5. Fuentes: adaptadores y pipeline de búsqueda

### Interfaz

```python
class Consulta(BaseModel):
    texto: str                       # consulta ya adaptada a la fuente
    especificaciones: list[Especificacion]
    precio_min: float | None
    precio_max: float | None
    estado: Literal["cualquiera", "nuevo", "reacondicionado", "segunda_mano"]

class OfertaCruda(BaseModel):
    url: str; titulo: str; precio: float | None; envio: float | None
    moneda: str = "EUR"; estado_producto: str | None; disponibilidad: str | None
    vendedor: str | None; valoracion: float | None; n_valoraciones: int | None
    imagen_url: str | None; texto_extra: str | None; ean: str | None; asin: str | None

class FuenteAdapter(Protocol):
    slug: str
    nivel: Literal["A", "B", "C", "D"]
    politica: Politica                # dominio, robots, rate limit, ttl caché
    def adaptar_consulta(self, c: Consulta) -> str: ...
    async def buscar(self, c: Consulta, ctx: Contexto) -> list[OfertaCruda]: ...
```

- Registro por descubrimiento: cada fichero en `app/fuentes/*.py` con una clase `Adaptador` se registra por `slug`. La tabla `herramientas.adaptador` apunta al slug; si es `null`, se usa `universal` (nivel C) si hay `url_plantilla_busqueda`, o `enlace` (nivel D).
- `Contexto` da acceso a `http` (cliente con caché, robots y rate limit ya aplicados), `ia` (agentes), `log` (eventos) y `presupuesto`.

### Adaptadores previstos

| slug | Nivel | Técnica | Fase |
|---|---|---|---|
| `enlace` | D | Sustituye `{q}`; devuelve una «oferta» de tipo enlace | F2 |
| `universal` | C | `http.markdown(url)` (httpx + conversión propia; Firecrawl si la página necesita JS) → Extractor → `list[OfertaCruda]` | F4 |
| `ebay` | A | Browse API `item_summary/search` con filtros `price`, `conditions`, `deliveryCountry=ES`; OAuth client-credentials cacheado | F3 |
| `google-shopping` | A | Serper `/shopping` (`gl=es`, `hl=es`) | F3 |
| `geizhals` | B | HTML estático; filtros por URL (`?fs=`); parse de listado | F3 |
| `idealo` | B | HTML de resultados; **[SUPUESTO]** servible sin JS; plan B: nivel C con Firecrawl | F3 |
| `pccomponentes` | B/C | **[SUPUESTO]** Cloudflare → primero probar nivel C con Firecrawl; si robots lo prohíbe, D | F3 |
| `chollometro` | B | RSS de búsqueda (`/rss/busqueda?q=`) **[SUPUESTO]** ruta exacta; plan B: HTML | F3 |
| `keepa` | A | Product Finder + precios actuales de Amazon.es (dominio 9); opcional por coste | F8 |
| `apify` | A | Actor genérico (`apify/web-scraper`) para fuentes que fallen en C | F8 |
| `reddit` | A | API oficial (`/r/<sub>/search`), solo para el Investigador | F6 |
| `kelkoo`, `coolmod`, `backmarket`, `mediamarkt`, `geeknetic` | C→B | Empiezan en universal; se promocionan a B cuando se les escribe parser | F4/F8 |

### Pipeline de una búsqueda

```
POST /busquedas
  1. (opcional) Intérprete: texto → especificaciones + rango + consultas_por_fuente   [caché por hash]
  2. Crear busqueda(en_curso) y busqueda_fuentes(pendiente) por cada fuente activa seleccionada
  3. asyncio.gather con semáforo (4 fuentes a la vez), timeout 20 s por fuente, 60 s global
       por fuente: caché? → robots → rate limit → adaptador.buscar → OfertaCruda[]
  4. Normalizar: precio+envío, moneda, estado, URL canónica (sin utm), hash
  5. Atributos: regex/heurísticas (RAM, GB, TB, CPU, W, pulgadas) → si faltan claves pedidas, Extractor en lote
  6. Puntuar: por especificación (numérica mín/máx/igual, booleana, texto) con peso; desconocido = 0,5 y marca «sin datos»;
     precio fuera de rango = filtro duro salvo `mostrar_fuera_rango`
  7. Dedupe/agrupar: EAN/ASIN → clave canónica; si no, rapidfuzz token_set_ratio ≥ 90 → mismo producto;
     75–90 → LLM-judge (Haiku) en lote; guardar productos/ofertas/precios
  8. Facetas: recuento por fuente, RAM, disco, estado, apto 24/7
  9. Marcar terminada; el frontend ya venía pintando resultados parciales desde el paso 3
```

Requisitos blandos («24/7») se puntúan con heurística en el paso 6 (TDP ≤ 25 W, fanless, formato mini) y se enriquecen con el Investigador solo a petición (botón «¿Aguanta 24/7?») o para el top 5 si la búsqueda lo pide.

## 6. IA y agentes

Todo en `app/ia/` tras una fachada `Agente` que añade: caché en `informes` por hash de entrada, contador en `costes_api`, corte por presupuesto, reintentos con `tenacity`, `fallbacks: "default"` (beta `server-side-fallback-2026-07-01`), y `stop_reason == "refusal"` tratado como resultado vacío registrado.

| Agente | Modelo y parámetros | Entrada → salida |
|---|---|---|
| **Intérprete** | `claude-opus-5`, `thinking: adaptive`, `output_config.effort: "medium"`, `output_config.format` con esquema `Interpretacion` | Texto libre → `{categoria, especificaciones:[{clave, operador, valor, unidad, peso, blando}], precio_min, precio_max, consultas_por_fuente:{slug: texto}, resumen_es}`; el system prompt (con la lista de claves de atributos conocidas) lleva `cache_control` |
| **Extractor** | `claude-haiku-4-5` (con `budget_tokens` solo si hace falta pensar; normalmente sin thinking), `output_config.format` con `list[Atributos]` o `list[OfertaCruda]`; `claude-sonnet-5` como reintento si la validación pydantic falla | (a) lote de hasta 40 títulos+descripciones → atributos; (b) markdown de una página de resultados → ofertas |
| **Investigador** | `claude-opus-5`, `web_search_20260209` + `web_fetch_20260209` con `allowed_domains` = dominios de la categoría «Comunidades y reviews» + fabricante, `max_uses: 8`, `citations: {enabled: true}`, streaming | `{producto, requisito}` → `{veredicto: apto\|no_apto\|dudoso, confianza 0–1, motivos:[…], citas:[{url, cita}], consumo_w?, ruido?}`; caché 30 días |
| **Comparador** | `claude-opus-5`, effort `low`, salida estructurada | N productos con atributos y ofertas → `{tabla:[…], pros_contras:{id:[…]}, recomendacion}` |
| **Reparador** | `claude-opus-5`, effort `high`, `web_fetch` desactivado (trabaja sobre la fixture) | HTML guardado + parser actual + error → `{selectores_nuevos, diff_propuesto, confianza}`; el workflow abre PR con el diff y la fixture como test |

Evaluación: `app/ia/evaluacion/consultas.jsonl` (20 consultas con interpretación esperada; se amplía con la tabla `ejemplos`). `pytest -m ia` corre solo con `ANTHROPIC_API_KEY` presente y se lanza a mano.

## 7. Anti-bloqueo respetuoso

Implementado una sola vez en `app/http.py` y usado por todos los adaptadores:

- **robots.txt**: `urllib.robotparser` con caché 24 h en `cache_http`; `can_fetch(UA, url)` falso → adaptador degradado a D y evento `robots_bloquea`.
- **Rate limit**: token bucket por dominio (1 petición / 2 s, ráfaga 2), configurable en `Politica`.
- **Backoff**: `tenacity` exponencial (1, 2, 4, 8 s) en 429/5xx/timeout; respeta `Retry-After`.
- **Circuit breaker**: 3 fallos seguidos → abierto 30 min → semiabierto con 1 petición de prueba. Estado en memoria + evento.
- **Caché HTTP**: por URL normalizada, TTL por política; las búsquedas repetidas en < 6 h no tocan la fuente.
- **User-Agent**: `buscaproducto/1.0 (+https://github.com/npiobject-labs/buscaproducto)`; `Accept-Language: es-ES`.
- **Detección de bloqueo**: 403/503 con HTML de Cloudflare/CAPTCHA → evento `anti_bot` y degradación a D en esa búsqueda; nunca reintento agresivo.

## 8. Tareas programadas: vigilar y cosechar

- `vigilar.yml` (cron diario 07:00 UTC + `workflow_dispatch`): `curl -X POST https://<app>.fly.dev/api/v1/tareas/vigilar -H "X-Clave: ${{ secrets.BP_CLAVE }}"`. El backend refresca las ofertas `vigilada=1` (las de alertas activas y las del top 10 de las últimas 5 búsquedas), añade filas a `precios` si cambió el precio, evalúa alertas y envía Telegram (`sendMessage` con enlace y gráfico en texto). Falla el job si la respuesta no es 200.
- `cosechar.yml` (cron nocturno 03:00 UTC): checkout, `uv sync --group cosecha`, `playwright install chromium`, y `python -m app.cosecha` que: pide al backend la lista de ofertas/fuentes que requieren navegador, las visita con Playwright (mismos límites de §7), y devuelve `POST /tareas/cosecha`. Si un adaptador con parser da 0 resultados y el HTML no es de bloqueo, guarda el HTML en `app/fuentes/fixtures/<slug>/AAAAMMDD.html`, llama al Reparador y abre una PR (`peter-evans/create-pull-request`) con el diff propuesto y la fixture. Nunca fusiona.
- Copia de seguridad (F8): `vigilar.yml` descarga `GET /exportar/copia.sqlite` (solo con clave) y lo sube como artifact 30 días **[SUPUESTO]** tamaño < 100 MB; plan B: snapshots del volumen de Fly.

## 9. Seguridad y secretos

| Secreto | Dónde vive | Quién lo usa |
|---|---|---|
| `BP_CLAVE` | Secreto del repo → `deploy.yml` lo pasa a Fly (`flyctl secrets set`) y `vigilar.yml`/`cosechar.yml` lo leen | Backend (`X-Clave`), crons |
| `ANTHROPIC_API_KEY` | Secreto del repo → Fly | Agentes |
| `SERPER_API_KEY`, `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET`, `FIRECRAWL_API_KEY`, `KEEPA_API_KEY`, `APIFY_TOKEN` | Secreto del repo → Fly | Adaptadores (cada uno opcional: sin clave, la fuente queda en D con evento `sin_clave`) |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Secreto del repo → Fly | Alertas |
| `FLY_API_TOKEN` | Heredado de la organización | `deploy.yml` |

- `deploy.yml` solo ejecuta `flyctl secrets set` para los secretos presentes (bucle sobre una lista, `--stage`), sin imprimirlos.
- Rate limit global del backend: 60 peticiones/min por IP; 5 búsquedas en curso como máximo.
- El frontend nunca contiene claves; la del backend la escribe el usuario en el móvil una vez.

## 10. Despliegue y verificación

- `app/Dockerfile`: `python:3.12-slim`, `uv` copiado de la imagen oficial, `uv sync --frozen --no-dev`, usuario sin privilegios, `CMD uvicorn app.main:app --host 0.0.0.0 --port 8080`.
- `app/fly.toml`: añade `[mounts] source="datos" destination="/datos"`; memoria 512 MB; `auto_stop_machines=true`, `min_machines_running=0`.
- `deploy.yml` (F2.1): paso «Crear volumen si falta» (`flyctl volumes list --json` → `flyctl volumes create datos --size 1 --region cdg --yes`), paso «Pasar secretos», y tras el despliegue **humo**: `/salud` con SHA (existe), `/holamundo` (existe), `GET /api/v1/herramientas` con clave → ≥ 30, `POST /api/v1/busquedas` en modo enlace con texto `minipc` → `terminada` en < 30 s.
- `tools/arrancar.ps1` se actualiza en F2.1 para `uv run uvicorn` en vez de `cargo run`; `CLAUDE.md` sección **Código** pasa a describir Python.

## 11. Tests

- `pytest` + `pytest-asyncio` + `respx` (mock de httpx). `ruff` para lint/format.
- **Contrato por adaptador**: `app/fuentes/fixtures/<slug>/*.html|json` + `test_<slug>.py` que comprueba ≥ N ofertas con precio y URL válidas. Un adaptador sin fixture no se fusiona.
- **Normalización y puntuación**: tablas de casos (`precio "1.299,00 €" → 1299.0`, `"16GB DDR5" → ram=16`).
- **API**: `httpx.AsyncClient(app=…)` contra SQLite temporal; búsqueda en modo enlace de principio a fin.
- **IA** (`-m ia`, manual): evaluación del Intérprete sobre `consultas.jsonl`; umbral 18/20.
- `ci.yml` corre `ruff check`, `ruff format --check`, `pytest -m "not ia"` en push y PR.

## 12. Estructura de carpetas

```
app/
  pyproject.toml  uv.lock  Dockerfile  fly.toml  .dockerignore
  app/
    main.py            # FastAPI, rutas /, /salud, /holamundo y router /api/v1
    config.py          # BP_* y presupuestos
    bd.py  migraciones/NNN.sql  seed/herramientas.json
    api/               # routers: herramientas, busquedas, ofertas, productos, alertas, tareas, eventos
    dominio/           # modelos pydantic: Consulta, Especificacion, OfertaCruda, Oferta, Producto
    busqueda/          # pipeline: orquestador, normalizar, atributos, puntuar, agrupar, facetas
    fuentes/           # registro + un fichero por adaptador + fixtures/
    http.py            # cliente con robots, rate limit, caché, breaker
    ia/                # fachada Agente + interprete, extractor, investigador, comparador, reparador + evaluacion/
    tareas/            # vigilar, cosecha, telegram, exportar
  tests/
docs/
  index.html  manifest.webmanifest  sw.js  mocks/  bitacora/  planificacion/
.github/workflows/
  pages.yml  deploy.yml  ci.yml  vigilar.yml  cosechar.yml  robots.yml  verificar-enlaces.yml
```
