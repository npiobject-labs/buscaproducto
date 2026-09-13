# BuscaProducto — Plan maestro

> Documento maestro del proyecto. Detalle técnico en [ARQUITECTURA.md](ARQUITECTURA.md), fuentes en [CATALOGO_HERRAMIENTAS.md](CATALOGO_HERRAMIENTAS.md), decisiones en [DECISIONES.md](DECISIONES.md) y sesión a sesión en [HOJA_DE_RUTA.md](HOJA_DE_RUTA.md).
>
> Sustituye al `PLAN.md` del proyecto local en Windows (Fases 1–2 hechas allí). Aquí todo corre en la nube: frontend en GitHub Pages, backend en Fly.io, desarrollo desde sesiones de claude.ai/code. Las suposiciones no verificadas van marcadas como **[SUPUESTO]** con su plan B.

## Índice

1. [Visión](#1-visión)
2. [Qué significa «el mejor buscador posible»](#2-qué-significa-el-mejor-buscador-posible)
3. [Alcance](#3-alcance)
4. [Requisitos](#4-requisitos)
5. [Caso de aceptación](#5-caso-de-aceptación)
6. [Fases](#6-fases)
7. [Estrategia de fuentes: API, scraping, IA universal, enlace](#7-estrategia-de-fuentes)
8. [Estrategia de IA](#8-estrategia-de-ia)
9. [Legalidad y respeto a las fuentes](#9-legalidad-y-respeto-a-las-fuentes)
10. [Costes](#10-costes)
11. [Riesgos y mitigaciones](#11-riesgos-y-mitigaciones)
12. [Verificación](#12-verificación)
13. [Lo que queda fuera (ideas futuras)](#13-ideas-futuras)

---

## 1. Visión

App personal para **encontrar el mejor producto y el mejor precio** a partir de una petición en lenguaje natural o de especificaciones estructuradas (`RAM ≥ 8 GB`, `disco ≥ 500 GB`, `apto 24/7`) y un rango de precios, agregando en una sola pantalla:

- **Ofertas reales** de comparadores, tiendas y marketplaces (APIs oficiales, scraping respetuoso y un adaptador universal con IA para cualquier web añadida a mano).
- **Comprensión** de lo que se pide (la IA convierte texto libre en especificaciones y explica cómo lo ha entendido).
- **Juicio** sobre requisitos que no salen en la ficha (¿aguanta 24/7?, ¿es silencioso?), con un agente que investiga reviews y comunidades y cita sus fuentes.
- **Memoria**: histórico de precios, «¿es buen precio ahora?», alertas por Telegram.

Modo híbrido: consulta en vivo bajo demanda + caché + histórico en SQLite. Uso personal, un solo usuario, desde el móvil.

## 2. Qué significa «el mejor buscador posible»

Es la **definición de hecho global**: el proyecto se da por terminado cuando se cumplen las 9 líneas. Cada una se mapea a fases concretas en §6.

| # | Criterio | Cómo se comprueba | Fases |
|---|---|---|---|
| C1 | **Entrada natural y estructurada.** Acepta texto libre («minipc 8gb para tener 24/7 por menos de 300») y lo convierte en especificaciones editables + rango de precio; también se puede rellenar a mano. Muestra siempre «lo que he entendido». | Test de 20 consultas de ejemplo → ≥ 18 interpretadas bien | F4 |
| C2 | **Cobertura.** ≥ 12 fuentes devolviendo ofertas reales (API + scraping + IA universal). Cualquier herramienta añadida a mano con `url_plantilla_busqueda` produce ofertas reales, no solo un enlace. | Búsqueda de aceptación con ≥ 12 fuentes en `ok` | F3, F4 |
| C3 | **Calidad de resultado.** Ofertas normalizadas (precio + envío, estado, disponibilidad), atributos extraídos (RAM, disco, CPU, TDP…), puntuación 0–100 con explicación por especificación, deduplicación y agrupación por producto con «mejor precio» y «nº de tiendas». | Test de contrato con fixtures; revisión manual del caso MiniPC | F3, F4 |
| C4 | **Confianza en el precio.** Histórico por oferta, gráfico, mínimo histórico, veredicto «buen precio / normal / caro» respecto a mediana e histórico. | `precios` se puebla al repetir búsquedas; gráfico visible | F5 |
| C5 | **Requisitos blandos.** Para «24/7», «silencioso», «fiable»: veredicto por modelo con citas a reviews/comunidades, cacheado, con nivel de confianza. | Informe visible para ≥ 5 modelos del caso MiniPC con ≥ 2 citas cada uno | F6 |
| C6 | **Vigilancia.** Alertas de precio objetivo y de «nueva oferta que cumple»; comprobación diaria automática; aviso por Telegram. | Cron en verde y mensaje recibido | F5 |
| C7 | **UX desde el móvil.** PWA instalable, resultados progresivos por fuente (< 3 s con caché), filtros y facetas, comparador lado a lado, compartir búsqueda por URL, exportar CSV, errores por fuente sin romper la página, accesibilidad AA. | Checklist §12 en móvil real | F1, F7 |
| C8 | **Operación sostenible.** Coste mensual acotado con contador por proveedor, robots.txt vinculante, rate limit, circuit breaker, tests de contrato, alerta cuando un adaptador devuelve 0 de forma anómala, propuesta de reparación asistida por IA en PR. | `ci.yml` verde; evento en bitácora del backend | F8 |
| C9 | **Extensible sin código y con poco código.** Alta manual en la web; adaptador nuevo = 1 fichero + 1 fixture + 1 test. | Añadir una fuente nueva en < 1 sesión | F2, F8 |

## 3. Alcance

**Dentro:** todo lo de §2; catálogo de ≥ 30 herramientas; alta manual; histórico y alertas; agentes IA de interpretación, extracción, investigación y reparación; PWA en Pages; backend en Fly; cosechador programado en GitHub Actions.

**Fuera (explícito):** compra automática o pagos; multiusuario; granjas de proxies, resolución de CAPTCHA o evasión de anti-bot; redistribución comercial de datos; búsqueda por imagen y extensión de navegador (ideas futuras, §13).

## 4. Requisitos

### Funcionales

| ID | Requisito | Fase |
|---|---|---|
| RF-01 | Búsqueda por texto libre | F1 |
| RF-02 | Especificaciones estructuradas clave:valor:operador añadibles/eliminables | F1 |
| RF-03 | Rango de precios mín–máx en euros con validación `mín ≤ máx` | F1 |
| RF-04 | Selección de fuentes por búsqueda, agrupadas por categoría | F1 |
| RF-05 | Catálogo de herramientas en categorías, con nivel de integración visible (API / scraping / IA universal / enlace) | F2 |
| RF-06 | Alta, edición y borrado manual de herramientas (`origen = usuario`), persistidas en la BD | F2 |
| RF-07 | Activar/desactivar herramientas predefinidas | F2 |
| RF-08 | Búsqueda asíncrona con progreso por fuente y resultados progresivos | F2 |
| RF-09 | Ofertas reales de fuentes API y scraping respetuoso | F3 |
| RF-10 | Normalización, extracción de atributos, puntuación explicada, deduplicación y agrupación por producto | F3, F4 |
| RF-11 | Filtros: precio, RAM, almacenamiento, fuente, apto 24/7, estado; facetas calculadas sobre los resultados | F3, F7 |
| RF-12 | Ordenación: precio ↑/↓, puntuación, valoración, «mejor relación» | F3 |
| RF-13 | Interpretación IA de la consulta en lenguaje natural → especificaciones + rango, con «lo que he entendido» editable | F4 |
| RF-14 | Adaptador universal IA: cualquier herramienta con `url_plantilla_busqueda` devuelve ofertas reales | F4 |
| RF-15 | Histórico de precios por oferta con gráfico y veredicto de precio | F5 |
| RF-16 | Alertas de precio objetivo y de nueva oferta, comprobación diaria, Telegram | F5 |
| RF-17 | Informe IA por producto para requisitos blandos (24/7…) con citas | F6 |
| RF-18 | Comparador lado a lado con pros/contras generados por IA | F6 |
| RF-19 | Compartir búsqueda por URL; exportar CSV; PWA instalable | F7 |
| RF-20 | Caso MiniPC precargado como ejemplo en el formulario | F1 |
| RF-21 | Presupuesto mensual por proveedor de API con corte automático | F8 |

### No funcionales

| ID | Requisito |
|---|---|
| RNF-01 | Frontend 100 % estático en `docs/`, sin CDNs, sin claves; funciona por `file://` en modo demo |
| RNF-02 | Interfaz en español, formatos `es-ES` |
| RNF-03 | Scraping respetuoso: robots.txt vinculante, ≤ 1 petición/2 s por dominio, User-Agent honesto, caché primero, `Retry-After` respetado |
| RNF-04 | Persistencia en SQLite sobre volumen de Fly; copia de seguridad diaria a GitHub Actions artifact **[SUPUESTO]** (plan B: `flyctl volumes snapshots`, automáticos y gratuitos) |
| RNF-05 | Backend protegido por una clave (`X-Clave`), única, guardada como secreto de Fly; sin cuentas de usuario |
| RNF-06 | Accesibilidad AA; roles ARIA en pestañas y modales; usable a 375 px |
| RNF-07 | Toda verificación de despliegue la hace un workflow (el sandbox no llega a Pages ni Fly) |
| RNF-08 | Coste total objetivo ≤ 15 €/mes en uso personal (§10) |

## 5. Caso de aceptación

> **MiniPC · RAM ≥ 8 GB · funcionamiento 24/7 · disco ≥ 500 GB · 130–330 €**

- Precarga formulario, filtros y datos fake del mock (F1).
- F3: la búsqueda real devuelve ofertas de **≥ 2 fuentes**; F4: **≥ 8**; cierre: **≥ 12**.
- «24/7» es el ejemplo de requisito blando: heurística (TDP ≤ 25 W, pasivo, chasis metálico) + agente investigador con citas (ServeTheHome TinyMiniMicro, NotebookCheck, r/MiniPCs, r/HomeServer).
- Se añaden **dos casos más** para no sobreajustar: «portátil 16 GB, 14", < 700 €, pantalla mate» y «router WiFi 6 con OpenWrt, < 120 €». Sirven para tests de interpretación y de extracción de atributos fuera del dominio MiniPC.

## 6. Fases

| Fase | Nombre | Sesiones | Entregable | Criterio de cierre (verificable) |
|---|---|---|---|---|
| **F0** ✅ | Planificación | 1 | Los 5 documentos de `docs/planificacion/` | Pages publica los `.md`; bitácora con la sesión |
| **F1** | Mock en Pages | 2 | `docs/index.html` (3 pestañas, 12 MiniPCs fake, localStorage), archivos en `docs/mocks/` | Checklist de mock (§12) en móvil real; build `BU-B1-…` nuevo |
| **F2** | Backend núcleo | 3 | `app/` en Python (FastAPI) sustituyendo al Rust; SQLite en volumen; seed del catálogo; CRUD; clave; búsquedas asíncronas en modo `enlace_manual`; frontend conectado | `deploy.yml` verde con `/salud` y humo de `/api/v1/herramientas` (≥ 30); búsqueda desde el móvil devuelve enlaces por fuente |
| **F3** | Fuentes reales | 4 | Núcleo de adaptadores (robots, rate limit, caché, circuit breaker); eBay Browse; Google Shopping vía Serper; scraping de Geizhals, Idealo, PcComponentes, Chollometro RSS; normalización; matching heurístico; dedupe | Caso MiniPC con ≥ 2 fuentes reales; `precios` se puebla al repetir; tests de contrato verdes en `ci.yml` |
| **F4** | IA de comprensión y extracción | 3 | Interpretar consulta (Opus 5, salida estructurada); extracción de atributos en lote (Haiku 4.5); adaptador universal (Firecrawl/crawl4ai → IA) para cualquier `{q}`; LLM-judge de dedupe | 20 consultas → ≥ 18 bien; ≥ 8 fuentes en `ok`; herramienta añadida a mano devuelve ofertas |
| **F5** | Histórico, alertas, vigilancia | 2 | Gráfico SVG; veredicto de precio; alertas; cron diario en GitHub Actions; Telegram | Cron verde; mensaje de Telegram recibido en el móvil |
| **F6** | Agente investigador | 2 | Informe 24/7 por modelo con `web_search`/`web_fetch` y citas; comparador lado a lado con pros/contras | ≥ 5 informes con ≥ 2 citas; comparador funcional |
| **F7** | Web real completa | 2 | PWA (manifest + service worker), facetas, compartir URL, CSV, progreso y errores por fuente, accesibilidad | Checklist §12 completa en móvil; Lighthouse PWA instalable **[SUPUESTO]** (plan B: comprobación manual «Añadir a pantalla de inicio») |
| **F8** | Robustez y operación | 3 | Presupuesto por API; cosechador Playwright en runner de Actions; alerta de «0 resultados anómalo»; reparación de selectores asistida por IA (PR); copia de seguridad | `ci.yml` + `cosechar.yml` + `vigilar.yml` verdes 7 días seguidos; C8 y C9 cumplidos |
| **F9** | Cierre | 1 | Revisión de los 9 criterios, README del proyecto, vídeo/capturas en `docs/` | Los 9 criterios de §2 marcados |

Total estimado: **23 sesiones**. Orden estricto F1 → F5; F6, F7 y F8 pueden intercalarse. Detalle por sesión, con prompt de arranque, en [HOJA_DE_RUTA.md](HOJA_DE_RUTA.md).

## 7. Estrategia de fuentes

Cada herramienta del catálogo tiene un **nivel de integración**, del más fiable al menos:

| Nivel | Nombre | Cómo | Ejemplos |
|---|---|---|---|
| **A** | API oficial o de terceros | Cliente HTTP con clave; sin scraping | eBay Browse, Serper (Google Shopping), Keepa (Amazon), Apify (actores), Reddit API |
| **B** | Scraping propio respetuoso | httpx + selectolax si el HTML es estático; Playwright solo en el cosechador de Actions | Geizhals, Idealo, Kelkoo, Coolmod, Back Market, Chollometro (RSS) |
| **C** | Adaptador universal IA | Página de resultados → markdown limpio (httpx o Firecrawl) → extracción estructurada con Claude → validación | Cualquier herramienta añadida a mano con `{q}`; MediaMarkt, Geeknetic |
| **D** | Enlace manual | Solo abre `url_plantilla_busqueda` con `{q}` | Wallapop, AliExpress, asistentes IA externos |

Reglas:

1. Si existe API oficial, **no se scrapea** (Amazon → Keepa; Google → Serper).
2. Toda herramienta B y C pasa por `robots.txt`; si está prohibido, cae automáticamente a **D** y queda registrado.
3. Toda herramienta nace en **D** al añadirse a mano y sube a **C** sola en cuanto la primera extracción IA devuelve ≥ 1 oferta válida. Subir a **B** o **A** es escribir un adaptador (1 fichero).
4. Las fuentes con anti-bot agresivo (Amazon directo, Google directo, Wallapop) se quedan en D o A: nunca se intenta evadir.

## 8. Estrategia de IA

Cuatro agentes con responsabilidades separadas, todos vía el SDK oficial de Anthropic (detalle en [ARQUITECTURA.md §6](ARQUITECTURA.md#6-ia-y-agentes)):

| Agente | Qué hace | Modelo | Cuándo corre |
|---|---|---|---|
| **Intérprete** | Texto libre → `{especificaciones, precio_min, precio_max, categoria, consultas_por_fuente}` con salida estructurada; devuelve «lo que he entendido» | `claude-opus-5`, thinking adaptativo, effort `medium` | Al lanzar una búsqueda con texto libre (1 llamada, cacheada por hash del texto) |
| **Extractor** | Título + descripción cruda → atributos normalizados (RAM, disco, CPU, TDP, tamaño, estado); página de resultados en markdown → lista de ofertas (adaptador universal) | `claude-haiku-4-5` (en lote); `claude-sonnet-5` si Haiku falla la validación | Por oferta sin atributos; por página en nivel C. Batch API en el cosechador nocturno (50 % coste) |
| **Investigador** | Requisitos blandos («24/7») por modelo: busca en comunidades y reviews, devuelve veredicto + confianza + citas; pros/contras para el comparador | `claude-opus-5` con `web_search_20260209` + `web_fetch_20260209` acotados a dominios del catálogo, `max_uses` 8 | Bajo demanda por producto; caché 30 días |
| **Reparador** | Adaptador con 0 resultados anómalo → propone selectores nuevos a partir del HTML guardado como fixture; el workflow abre una PR, nunca la fusiona | `claude-opus-5`, effort `high` | Desde `cosechar.yml` cuando salta la alerta |

Principios: salida estructurada (`output_config.format`) y `strict: true` en herramientas; prompt caching en los system prompts largos (catálogo de atributos); `fallbacks: "default"` activado; presupuesto mensual y contador de tokens en `costes_api`; ninguna llamada IA en el camino crítico si hay caché; el usuario puede corregir cualquier interpretación y la corrección se guarda como ejemplo para evaluación.

## 9. Legalidad y respeto a las fuentes

- `robots.txt` vinculante (caché 24 h); rate limit por dominio; `User-Agent: buscaproducto/1.0 (+https://github.com/npiobject-labs/buscaproducto)`; backoff exponencial; circuit breaker (3 fallos → 30 min).
- Uso personal, sin redistribución; los datos no salen del backend salvo al propio navegador del usuario.
- Preferencia por APIs oficiales; columna `politica_scraping` en el catálogo; `robots.yml` verifica mensualmente y guarda el resultado en `docs/planificacion/robots.md`.
- Sin proxies rotatorios, sin resolución de CAPTCHA, sin suplantar navegadores.

## 10. Costes

Estimación mensual en uso personal (unas 150 búsquedas/mes + cosecha diaria de 50 ofertas vigiladas). Precios de terceros **[SUPUESTO]**: se confirman al dar de alta cada clave y se anotan en DECISIONES.md.

| Partida | Estimación | Notas |
|---|---|---|
| Fly.io: 1 máquina `shared-cpu-1x` 512 MB con auto-stop + volumen 1 GB | 2–4 € | Se apaga sola; el cron la despierta |
| Anthropic API (Opus 5 para interpretar/investigar, Haiku 4.5 para extraer) | 3–6 € | Opus 5: 5 $/25 $ por MTok; Haiku 4.5: 1 $/5 $; caché y Batch reducen |
| Serper.dev (Google Shopping) | 0–5 € | 2.500 créditos gratis; después ≈ 1 $/1.000 |
| eBay Browse API | 0 € | Gratis con límite diario amplio |
| Firecrawl (páginas con JS en nivel C) | 0–16 € | 500 créditos gratis; plan de pago solo si hace falta |
| Keepa API (opcional, Amazon) | 0 o ≈ 19 € | Se activa solo si Amazon resulta imprescindible |
| Apify (opcional) | 0–5 € | Crédito mensual gratuito |
| Telegram, GitHub Actions, Pages | 0 € | Repo público |
| **Total objetivo** | **≤ 15 €/mes** sin Keepa | RF-21 corta las llamadas al superar el presupuesto |

## 11. Riesgos y mitigaciones

| Riesgo | Mitigación |
|---|---|
| Anti-bot (Cloudflare, CAPTCHA) en Amazon/Google/PcComponentes | No scrapear: Keepa/Serper; nivel C vía Firecrawl si robots lo permite; si no, D. Nunca evadir |
| Cambios de HTML rompen adaptadores | Selectores centralizados; fixtures + tests de contrato; alerta «0 anómalo»; Reparador propone PR |
| Máquina de Fly apagada (auto-stop) → primera petición lenta | Aceptado (2–5 s); el frontend muestra «despertando»; el cron la despierta antes de la cosecha |
| Playwright no cabe en Fly (imagen y RAM) | Playwright solo en el cosechador de GitHub Actions (runner gratuito); en vivo, httpx + Firecrawl |
| Coste de IA se dispara | Presupuesto por proveedor (RF-21), caché por hash, Haiku para lo masivo, Batch API en nocturno |
| Sandbox sin acceso a Pages/Fly/webs externas | Toda verificación en workflows; `robots.yml` y `verificar-enlaces.yml` en runner |
| Migrar de Rust a Python rompe la plantilla (`deploy.yml`, `arrancar.ps1`) | Mantener contratos `/`, `/salud`, `/holamundo`, puerto 8080, `BUILD_ID`; actualizar `arrancar.ps1` y CLAUDE.md en la misma sesión (F2.1) |
| Backend público en internet con claves de pago dentro | Clave `X-Clave` obligatoria en `/api/*`; rate limit global; secretos solo en Fly |
| Sobreajuste al caso MiniPC | Tres casos de aceptación (§5); tests de interpretación con 20 consultas variadas |
| Scope creep | Fases con criterio medible; §13 recoge lo que no entra |

## 12. Verificación

**Regla general (CLAUDE.md):** nada se da por desplegado hasta que el run del workflow para el SHA enviado está en `success` según la API de GitHub Actions.

**Workflows de verificación previstos** (se crean en la fase indicada):

| Workflow | Qué comprueba | Fase |
|---|---|---|
| `pages.yml` (existe) | Publica `docs/`; genera índices de bitácora y mocks | — |
| `deploy.yml` (existe, se amplía) | `/salud` con SHA; `/holamundo`; **nuevo:** `/api/v1/herramientas` ≥ 30, búsqueda de humo en `enlace_manual`, crea el volumen si falta, pasa los secretos | F2 |
| `ci.yml` | ruff + pytest (tests de contrato con fixtures) en cada PR y push | F3 |
| `robots.yml` | Descarga `robots.txt` de cada dominio del catálogo y escribe `docs/planificacion/robots.md` | F3 |
| `verificar-enlaces.yml` | Cada `url_plantilla_busqueda` con `{q}=minipc` responde 200/3xx | F2 |
| `vigilar.yml` | Cron diario: llama a `/api/v1/tareas/vigilar` (alertas + histórico) | F5 |
| `cosechar.yml` | Cron nocturno: Playwright en el runner para fuentes que lo necesiten; sube ofertas al backend; dispara el Reparador si hay «0 anómalo» | F8 |

**Checklist del mock y de la web (móvil real, 375 px, y escritorio):**

1. Carga sin pantalla en blanco; consola limpia; en modo demo cero peticiones externas.
2. Tres pestañas (Búsqueda · Herramientas · Resultados); formulario precargado con el caso MiniPC.
3. Buscar → progreso por fuente → resultados progresivos.
4. Cada filtro altera la lista; el ítem de 349 € entra al subir el máximo; el de 4 GB cae por RAM; el de 256 GB por disco; «apto 24/7» excluye los no aptos.
5. Ordenaciones correctas; validación `mín ≤ máx`.
6. «+ Añadir herramienta»: validación, badge «Añadida por ti», aparece como fuente, persiste tras recargar; borrar pide confirmación.
7. Estado vacío + «Limpiar filtros».
8. Modal cierra con Escape y clic fuera.
9. Pestañas pasan a barra inferior en móvil.
10. (Web real) Clave guardada una vez; error por fuente visible sin romper; compartir URL reproduce la búsqueda; CSV descarga; «Añadir a pantalla de inicio» funciona.

## 13. Ideas futuras

Fuera del alcance actual: búsqueda por imagen (foto del producto → consulta), extensión de navegador, notificaciones push web, multiusuario, importar listas de deseos de Amazon, comparador de consumo eléctrico anual con tarifa propia.

## Glosario

- **Adaptador**: clase Python que consulta una fuente y devuelve ofertas crudas.
- **Nivel de integración**: A (API), B (scraping propio), C (IA universal), D (enlace manual).
- **Oferta**: producto concreto, a un precio, en una fuente, en un momento.
- **Producto**: agrupación de ofertas del mismo artículo (clave canónica marca+modelo o EAN/ASIN).
- **Matching**: puntuación 0–100 de cuánto cumple una oferta las especificaciones, con explicación por especificación.
- **Cosechador**: workflow programado que refresca precios y corre Playwright en el runner de GitHub.
- **Requisito blando**: el que no sale en la ficha (24/7, silencioso) y necesita al Investigador.
