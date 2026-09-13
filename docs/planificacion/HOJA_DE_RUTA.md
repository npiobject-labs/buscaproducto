# Hoja de ruta sesión a sesión

> Cada línea es **una sesión de claude.ai/code desde el móvil**. Lleva objetivo, entregables, criterio verificable y un **prompt de arranque** listo para pegar. Se marca `[x]` al cerrar la sesión (junto con el resumen en `sesiones/` y la entrada de bitácora). Orden estricto F1 → F5; F6/F7/F8 pueden intercalarse.
>
> Convenciones: todo cambio acaba en `main`; el build del mock sube en cada iteración (`BU-B1-AAAAMMDD-NNN`); nada se anuncia sin run en `success`.


## Estado tras la sesión del 13-09-2026 (desarrollo de principio a fin)

Todo el código de F1–F8 está escrito, probado (33 tests, `ci.yml`) y desplegado desde la rama con `deploy.yml`. Lo que sigue **pendiente de verificación en vivo** depende de secretos que solo puede crear el usuario, o de decisiones de coste:

| Qué | Estado | Qué falta |
|---|---|---|
| Frontend (PWA, demo + real) | Hecho y probado con Playwright (27 comprobaciones de la checklist §12) | Probar en móvil real tras fusionar en `main` |
| Backend en Fly | Desplegado; `/salud` verificado por el workflow | Crear `BP_CLAVE` para que `/api/v1` responda (ahora 503) |
| eBay, Google Shopping (Serper) | Adaptadores con tests sobre respuestas grabadas | `EBAY_CLIENT_ID/SECRET`, `SERPER_API_KEY` |
| Chollometro | Parser sobre HTML real (fixture del runner) | Nada |
| Geizhals, Idealo, PcComponentes, Kelkoo, Coolmod, MediaMarkt, Back Market | Bloquean peticiones directas (403 anti-bot, ver `enlaces.md`) → nivel C | `FIRECRAWL_API_KEY`, o dejar que el cosechador nocturno las visite con Chromium |
| IA (Intérprete, Extractor, universal, Investigador, Comparador, Reparador) | Código con tests sobre cliente simulado | `BP_IA_TOKEN` (gateway `apisor.oracle402.com`) o `ANTHROPIC_API_KEY`; evaluación 18/20 del Intérprete (`pytest -m ia`) |
| Alertas y Telegram | Hecho; `vigilar.yml` diario con copia de seguridad | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` |
| Cosechador y Reparador | Hecho; `cosechar.yml` nocturno abre PR en borrador | Primer run con `BP_CLAVE` |
| Keepa, Apify | **No implementados** (D-15): coste y sin forma de verificar | Decidir si Amazon compensa 19 €/mes |
| Sesión 9.1 (cierre por criterios) | Pendiente: exige los secretos anteriores para medir C1, C2, C5 y C6 en vivo | |

## F0 · Planificación

- [x] **0.1 Plan maestro** — `docs/planificacion/{PLAN, ARQUITECTURA, CATALOGO_HERRAMIENTAS, DECISIONES, HOJA_DE_RUTA}.md`. *Criterio:* Pages publica; bitácora con la sesión.

## F1 · Mock en Pages (2 sesiones)

- [x] **1.1 Mock completo** — Reconstruir `docs/index.html` según PLAN.md §12 (checklist 1–9): banner DEMO, 3 pestañas, formulario precargado con el caso MiniPC, catálogo de las 32 herramientas de búsqueda con toggles y alta manual en `localStorage`, 12 MiniPCs fake, filtros y ordenaciones reales. Archivar el mock 0 en `docs/mocks/000-mock0.html`. *Criterio:* run de `pages.yml` en `success`; checklist 1–9 en móvil.
  *Prompt:* «Sesión 1.1 de HOJA_DE_RUTA.md: construye el mock completo en docs/index.html siguiendo PLAN.md §12 y el catálogo; archiva el mock anterior; sube el build; publica y dime SHA, URL y build.»
- [x] **1.2 Lenguaje natural y comparador en el mock** — Campo único «¿Qué buscas?» con «lo que he entendido» simulado (regex local), selección múltiple de tarjetas → comparador lado a lado, gráfico SVG de histórico fake, estado «despertando backend». Sirve de especificación visual de F4–F6. *Criterio:* checklist + build nuevo.
  *Prompt:* «Sesión 1.2: añade al mock el campo de lenguaje natural con interpretación simulada, el comparador lado a lado y el gráfico SVG de histórico con datos fake. Archiva, sube build, publica.»

## F2 · Backend núcleo (3 sesiones)

- [x] **2.1 FastAPI en Fly** — Sustituir `app/` (Rust) por Python: `pyproject.toml` (uv), `Dockerfile`, `fly.toml` con volumen, `main.py` con `/`, `/salud`, `/holamundo` idénticos, `/api/v1/salud-bd`. `deploy.yml`: crear volumen si falta y pasar secretos presentes. Actualizar `tools/arrancar.ps1` y la sección **Código** de `CLAUDE.md`. Añadir `ci.yml` (ruff + pytest). *Criterio:* `deploy.yml` en `success` (los pasos de `/salud` y `/holamundo` existentes pasan); `ci.yml` verde.
  *Prompt:* «Sesión 2.1: migra app/ a Python FastAPI según ARQUITECTURA.md §3 y §10 (D-01), manteniendo los contratos de la plantilla; amplía deploy.yml con volumen y secretos; crea ci.yml; actualiza arrancar.ps1 y CLAUDE.md. Verifica el run y dame SHA y URL de /salud.»
- [x] **2.2 BD, seed y catálogo** — Migraciones, tabla `herramientas`, `app/seed/generar.py` que lee CATALOGO_HERRAMIENTAS.md → `herramientas.json`, CRUD `/api/v1/herramientas`, dependencia `requiere_clave`, CORS. Secreto `BP_CLAVE` en el repo (lo crea el usuario en Settings → Secrets; la sesión avisa). Humo en `deploy.yml`: `/api/v1/herramientas` ≥ 30. *Criterio:* humo verde.
  *Prompt:* «Sesión 2.2: migraciones SQLite en el volumen, seed generado desde el catálogo, CRUD de herramientas con clave X-Clave y CORS; humo en deploy.yml. Dime qué secretos tengo que crear.»
- [x] **2.3 Búsquedas asíncronas en modo enlace + frontend conectado** — `POST /busquedas`, progreso por fuente, adaptador `enlace`, `GET /busquedas/{id}/resultados`; `docs/index.html` en modo real (clave guardada, polling, resultados progresivos, catálogo desde la API, alta manual contra la BD). `verificar-enlaces.yml` comprueba cada `url_plantilla_busqueda` y corrige el catálogo. *Criterio:* búsqueda «minipc» desde el móvil termina con ≥ 25 enlaces; humo de búsqueda en `deploy.yml`.
  *Prompt:* «Sesión 2.3: búsquedas asíncronas con progreso por fuente en modo enlace, frontend conectado a la API con clave guardada, y workflow verificar-enlaces.yml. Publica y verifica.»

## F3 · Fuentes reales (4 sesiones)

- [x] **3.1 Núcleo de adaptadores** — `app/http.py` (robots, rate limit, backoff, breaker, caché), interfaz `FuenteAdapter`, registro por descubrimiento, normalización (precio, envío, estado, URL canónica, hash), atributos por regex, tabla `precios`, `robots.yml` → `docs/planificacion/robots.md`. Tests de normalización. *Criterio:* `ci.yml` verde; `robots.md` publicado.
  *Prompt:* «Sesión 3.1: implementa http.py con robots/rate limit/caché/breaker, la interfaz de adaptadores, normalización y atributos por regex con tests, y robots.yml. Verifica.»
- [x] **3.2 eBay Browse + Google Shopping (Serper)** — Adaptadores A con fixtures JSON y tests de contrato; filtros de precio y estado; secretos `EBAY_*`, `SERPER_API_KEY`. *Criterio:* caso MiniPC devuelve ofertas de 2 fuentes reales (criterio de la fase); tests verdes.
  *Prompt:* «Sesión 3.2: adaptadores eBay Browse y Serper shopping con fixtures y tests; dime qué secretos crear; verifica con el caso MiniPC.»
- [x] **3.3 Scraping respetuoso** — Geizhals e Idealo (nivel B, httpx + selectolax), PcComponentes (nivel C con Firecrawl si robots lo permite), Chollometro por RSS. Fixtures HTML reales obtenidas con un workflow puntual (`fixtures.yml`, `workflow_dispatch`) porque el sandbox no llega a las webs. *Criterio:* ≥ 4 fuentes reales en `ok`; eventos de robots y rate limit visibles en `/eventos`.
  *Prompt:* «Sesión 3.3: adaptadores Geizhals, Idealo, PcComponentes y Chollometro RSS con fixtures obtenidas por workflow; verifica y enséñame /eventos.»
- [x] **3.4 Puntuación, dedupe y facetas** — Puntuación por especificación con explicación, filtro duro de precio, agrupación por producto (EAN/ASIN, rapidfuzz), facetas, ordenaciones, filtros en el frontend contra la API. *Criterio:* el caso MiniPC muestra productos agrupados con «mejor precio» y «n tiendas»; `precios` se puebla al repetir la búsqueda; tests.
  *Prompt:* «Sesión 3.4: puntuación explicada, dedupe/agrupación por producto, facetas y ordenaciones en API y frontend. Verifica con el caso MiniPC repetido dos veces.»

## F4 · IA de comprensión y extracción (3 sesiones)

- [x] **4.1 Intérprete** — Fachada `Agente` (caché en `informes`, `costes_api`, presupuesto, fallbacks), Intérprete con `claude-opus-5` y salida estructurada, `POST /interpretar`, «lo que he entendido» editable en el frontend, tabla `ejemplos`, `consultas.jsonl` con 20 casos y `pytest -m ia`. *Criterio:* ≥ 18/20; consumo visible en `/costes`.
  *Prompt:* «Sesión 4.1: fachada Agente y el Intérprete según ARQUITECTURA.md §6 con la skill claude-api; evaluación de 20 consultas; frontend con "lo que he entendido". Ejecuta la evaluación y dame el resultado.»
- [x] **4.2 Extractor de atributos** — Haiku 4.5 en lote para ofertas sin atributos clave, reintento con Sonnet 5, LLM-judge de dedupe en la franja 75–90. *Criterio:* en el caso MiniPC, ≥ 90 % de ofertas con RAM y disco rellenos; tests con fixtures de respuestas grabadas.
  *Prompt:* «Sesión 4.2: Extractor de atributos en lote con Haiku 4.5 y LLM-judge de dedupe; mide la cobertura de atributos en el caso MiniPC.»
- [x] **4.3 Adaptador universal** — `http.markdown()` (httpx + conversión propia; Firecrawl con `necesita_js`), Extractor de páginas, promoción automática D → C, botón «Probar» en el catálogo. Promocionar Kelkoo, Coolmod, MediaMarkt, Back Market, Geeknetic. *Criterio:* ≥ 8 fuentes en `ok`; una herramienta añadida a mano desde el móvil devuelve ofertas.
  *Prompt:* «Sesión 4.3: adaptador universal IA con promoción automática y botón Probar; promociona las fuentes de nivel C del catálogo; verifica ≥ 8 fuentes en ok.»

## F5 · Histórico, alertas y vigilancia (2 sesiones)

- [x] **5.1 Histórico y veredicto de precio** — `GET /ofertas/{id}/historico`, mínimo/mediana, veredicto «buen precio / normal / caro», gráfico SVG en el frontend, marca `vigilada`. *Criterio:* gráfico con ≥ 3 puntos tras 3 días de `vigilar.yml`.
  *Prompt:* «Sesión 5.1: histórico de precios con gráfico SVG y veredicto de precio; endpoint y frontend. Verifica.»
- [x] **5.2 Alertas, cron y Telegram** — CRUD de alertas, `POST /tareas/vigilar`, `vigilar.yml` diario, envío por Telegram (`TELEGRAM_*`), alerta «nueva oferta que cumple». *Criterio:* run de `vigilar.yml` en `success` y mensaje recibido.
  *Prompt:* «Sesión 5.2: alertas de precio objetivo y nueva oferta, tarea vigilar, workflow diario y Telegram. Dime qué secretos crear y lanza el workflow.»

## F6 · Agente investigador (2 sesiones)

- [x] **6.1 Informe de requisitos blandos** — Investigador con `web_search`/`web_fetch` acotados a dominios de la categoría 6, citas, caché 30 días, botón «¿Aguanta 24/7?» y veredicto en la tarjeta; heurística TDP/fanless previa. *Criterio:* ≥ 5 informes con ≥ 2 citas en el caso MiniPC.
  *Prompt:* «Sesión 6.1: Investigador con web_search/web_fetch acotados y citas; endpoint de informe y botón en el frontend. Genera informes para el top 5 del caso MiniPC.»
- [x] **6.2 Comparador con pros y contras** — `POST /comparar`, tabla lado a lado, pros/contras y recomendación con Opus 5 effort `low`; enlaces a informes. *Criterio:* comparar 3 productos desde el móvil en < 15 s.
  *Prompt:* «Sesión 6.2: comparador lado a lado con pros/contras generados; frontend y endpoint. Verifica.»

## F7 · Web real completa (2 sesiones)

- [x] **7.1 PWA y compartir** — `manifest.webmanifest`, `sw.js` (solo estáticos), URL compartible `#b=`/`#q=`, exportar CSV, historial de búsquedas. *Criterio:* «Añadir a pantalla de inicio» funciona; URL compartida reproduce la búsqueda.
  *Prompt:* «Sesión 7.1: convierte docs/index.html en PWA, añade compartir por URL, CSV e historial. Publica y verifica.»
- [x] **7.2 Pulido y accesibilidad** — Errores por fuente visibles, estado «despertando», facetas dinámicas, foco y ARIA, contraste, 375/768/1280, modo oscuro. Checklist §12 completa. *Criterio:* checklist 1–10 marcada en la bitácora.
  *Prompt:* «Sesión 7.2: recorre la checklist de PLAN.md §12 en la web real y corrige todo lo que falle; accesibilidad y modo oscuro. Publica.»

## F8 · Robustez y operación (3 sesiones)

- [x] **8.1 Presupuesto y observabilidad** — RF-21 con corte por proveedor y degradación, `/costes` y `/eventos` en una pestaña «Estado» del frontend, alerta Telegram al 80 % del presupuesto, rate limit global por IP. *Criterio:* simular presupuesto agotado → búsqueda sigue con fuentes gratuitas y aviso.
  *Prompt:* «Sesión 8.1: presupuesto mensual por proveedor con corte y degradación, pestaña Estado con costes y eventos, aviso al 80 %. Verifica con un presupuesto de prueba.»
- [x] **8.2 Cosechador y copia de seguridad** — `cosechar.yml` con Playwright en el runner y `POST /tareas/cosecha`; `GET /exportar/copia.sqlite` y artifact diario; Keepa y Apify como adaptadores opcionales si hay clave. *Criterio:* run nocturno en `success` 3 días seguidos; artifact presente.
  *Prompt:* «Sesión 8.2: cosechador nocturno con Playwright en Actions, endpoint de cosecha, copia de seguridad diaria, adaptadores opcionales Keepa/Apify. Lanza el workflow y verifica.»
- [x] **8.3 Reparador y alerta de 0 anómalo** — Detección de «0 resultados anómalo» (media móvil por fuente), guardado de fixture, Reparador, PR automática en borrador, tests de contrato para cada fixture nueva. *Criterio:* provocar un fallo en un adaptador → PR creada con diff y fixture.
  *Prompt:* «Sesión 8.3: detección de 0 anómalo, Reparador con Opus 5 y PR automática desde cosechar.yml. Provoca un fallo y enséñame la PR.»

## F9 · Cierre (1 sesión)

- [ ] **9.1 Revisión de criterios** — Recorrer los 9 criterios de PLAN.md §2 con evidencia (run, captura, número); README del proyecto con capturas; sección «Cómo añadir una fuente» definitiva; lista de ideas futuras actualizada. *Criterio:* los 9 marcados en la bitácora.
  *Prompt:* «Sesión 9.1: revisa los 9 criterios de cierre con evidencia, actualiza README y deja la bitácora de cierre.»

---

## Secretos que tendrá que crear el usuario (Settings → Secrets and variables → Actions)

| Cuándo | Secreto | Dónde se consigue |
|---|---|---|
| 2.2 | `BP_CLAVE` | Cadena aleatoria larga (p. ej. `openssl rand -hex 24`); la misma se escribe una vez en la pestaña Estado de la web |
| 4.1 | `BP_IA_TOKEN` (o `ANTHROPIC_API_KEY`) y variable `BP_IA_BASE_URL` opcional | Token del gateway `apisor.oracle402.com` (D-13); si se usa la API de Anthropic directa, poner `BP_IA_BASE_URL=https://api.anthropic.com` |
| 3.2 | `SERPER_API_KEY` | serper.dev → API key |
| 3.2 | `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET` | developer.ebay.com → Application keys (producción) |
| 3.3 / 4.3 | `FIRECRAWL_API_KEY` | firecrawl.dev |
| 4.1 | `ANTHROPIC_API_KEY` | console.anthropic.com |
| 5.2 | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | @BotFather; chat id con @userinfobot |
| 8.2 (opcional) | `KEEPA_API_KEY`, `APIFY_TOKEN` | keepa.com/#!api · apify.com |

`deploy.yml` los pasa a Fly solo si existen; sin ellos la fuente correspondiente queda en nivel D con evento `sin_clave`.
