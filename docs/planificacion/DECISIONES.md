# Decisiones de arquitectura (ADR)

Formato corto: contexto → decisión → consecuencias → plan B. Las suposiciones sin verificar llevan **[SUPUESTO]**. Se añaden al final; nunca se reescriben las anteriores (se marcan «sustituida por D-nn»).

## D-01 · Backend en Python (FastAPI), sustituyendo al Rust de la plantilla

- **Contexto:** la plantilla trae `app/` en Rust (axum). El plan heredado y todo el ecosistema necesario (Playwright, crawl4ai, feedparser, SDK de Anthropic, selectolax, rapidfuzz) es Python. Un solo desarrollador, criterio de eficiencia.
- **Decisión:** `app/` pasa a Python 3.12 + FastAPI en F2.1, manteniendo los contratos de la plantilla (`/`, `/salud`, `/holamundo`, CORS, puerto 8080, `BUILD_ID`) para que `deploy.yml` siga funcionando sin tocar su verificación.
- **Consecuencias:** actualizar `Dockerfile`, `tools/arrancar.ps1` y la sección **Código** de `CLAUDE.md` en la misma sesión; imagen algo mayor (≈ 150 MB) y arranque en frío ≈ 2 s más.
- **Plan B:** mantener Rust como pasarela y un proceso Python `worker` en la misma máquina. Descartado salvo que Fly rechace la imagen Python por tamaño (no esperado).

## D-02 · Frontend estático en Pages hablando con Fly, no servido por FastAPI

- **Contexto:** el plan heredado servía el frontend desde FastAPI. Aquí Pages ya publica `docs/` en cada push y el sandbox no puede verificar nada más.
- **Decisión:** `docs/index.html` es la app real (PWA) y llama a `https://<app>.fly.dev/api/v1` con CORS y cabecera `X-Clave`. FastAPI no sirve HTML.
- **Consecuencias:** despliegues independientes (UI en segundos, backend en minutos); modo demo por `file://` gratis; el backend necesita CORS con `allow_headers`.
- **Plan B:** si CORS diera problemas con el service worker, servir también `docs/` desde FastAPI como espejo.

## D-03 · SQLite en volumen de Fly

- **Contexto:** un usuario, una máquina, datos pequeños (< 100 MB en años).
- **Decisión:** SQLite (WAL) en `/datos/buscaproducto.sqlite` sobre un volumen de 1 GB creado por `deploy.yml` si falta. Una sola máquina (`--ha=false`).
- **Consecuencias:** breve caída en cada despliegue (la máquina se reemplaza); copia de seguridad diaria como artifact **[SUPUESTO]** de tamaño razonable.
- **Plan B:** Turso/libSQL (gratis en su tramo básico) si el volumen complica los despliegues.

## D-04 · Protección con una única clave `X-Clave`

- **Contexto:** el backend es público en internet y contiene claves de APIs de pago; el plan excluye cuentas de usuario.
- **Decisión:** toda ruta `/api/*` exige la cabecera `X-Clave` igual al secreto `BP_CLAVE`. El usuario la escribe una vez en el móvil; se guarda en `localStorage`.
- **Consecuencias:** sin gestión de sesiones; rate limit global por IP como segunda barrera; `docs/` sigue sin contener secretos.
- **Plan B:** Cloudflare Access o token rotatorio si se detectara uso ajeno (evento `clave_invalida` repetido).

## D-05 · Tareas programadas con cron de GitHub Actions, no con la máquina de Fly encendida

- **Contexto:** `auto_stop_machines=true` y `min_machines_running=0` para no gastar; un scheduler interno no corre con la máquina apagada.
- **Decisión:** `vigilar.yml` (diario) y `cosechar.yml` (nocturno) llaman al backend con `curl` + `X-Clave`; la llamada despierta la máquina. Misma técnica que `vigilancia-fly.yml`.
- **Consecuencias:** latencia de minutos en las alertas (aceptable); todo queda registrado en runs de Actions verificables por API.
- **Plan B:** Fly Machines programadas (`fly machine run --schedule daily`) si el cron de Actions resultara poco fiable.

## D-06 · Playwright solo en el runner de GitHub Actions

- **Contexto:** Chromium en la imagen de Fly supone ≈ 400 MB y ≥ 1 GB de RAM; en repo público los minutos de Actions son gratuitos.
- **Decisión:** en vivo, nivel B con httpx + selectolax y nivel C con Firecrawl para páginas con JS; Playwright vive en `cosechar.yml` para seguimiento programado y para generar fixtures.
- **Consecuencias:** la búsqueda interactiva no depende de un navegador; las fuentes que solo funcionen con navegador se refrescan de noche.
- **Plan B:** máquina de Fly de 1 GB con Playwright si alguna fuente crítica no funciona ni con Firecrawl ni en diferido.

## D-07 · Proveedor de IA: Anthropic, con reparto de modelos por tarea

- **Contexto:** hay cuatro trabajos de IA con perfiles distintos de coste y dificultad.
- **Decisión:** `claude-opus-5` para Intérprete, Investigador, Comparador y Reparador (thinking adaptativo, effort por tarea); `claude-haiku-4-5` para extracción masiva y LLM-judge de dedupe, con `claude-sonnet-5` como reintento. Salida estructurada, prompt caching, `fallbacks: "default"`, Batch API en el cosechador nocturno. Presupuesto mensual con corte (RF-21).
- **Consecuencias:** coste estimado 3–6 €/mes; todas las salidas se validan con pydantic; toda respuesta se cachea en `informes`.
- **Plan B:** bajar el Intérprete a `claude-sonnet-5` si la evaluación (18/20) se mantiene; nunca cambiar de proveedor sin repetir la evaluación.

## D-08 · Google Shopping vía Serper.dev; Amazon vía Keepa opcional

- **Contexto:** Google y Amazon son hostiles al scraping; el catálogo los marca `hostil (usar API)`.
- **Decisión:** Serper (`/shopping`) desde F3 por precio; Keepa solo en F8 y solo si Amazon resulta imprescindible para el usuario (≈ 19 €/mes rompe el objetivo de coste).
- **Consecuencias:** Amazon queda en nivel D (enlace) hasta F8.
- **Plan B:** SerpAPI si Serper degrada; Apify actor de Amazon como alternativa a Keepa sin histórico.

## D-09 · Adaptador universal IA como camino por defecto de toda herramienta nueva

- **Contexto:** requisito central: añadir fuentes sin código. El enlace manual del plan heredado no devuelve ofertas.
- **Decisión:** toda herramienta con `url_plantilla_busqueda` se intenta en nivel C (página → markdown → Extractor → ofertas validadas) y se promociona sola de D a C al primer éxito. Escribir un parser (nivel B) es una optimización, no un requisito.
- **Consecuencias:** coste de IA por búsqueda en fuentes C (≈ 0,002 € por página con Haiku) y latencia +2–4 s; sujeto a robots y anti-bot igual que B.
- **Plan B:** cachear la estructura extraída por dominio («selectores aprendidos») para que la segunda búsqueda no use IA. Se implementa en F8 si el coste lo justifica.

## D-10 · Reparación de adaptadores asistida por IA, siempre vía PR

- **Contexto:** los cambios de HTML son el mayor coste de mantenimiento.
- **Decisión:** cuando `cosechar.yml` detecta «0 resultados anómalo», guarda el HTML como fixture, pide al Reparador un diff y abre una PR en borrador. Nadie fusiona automáticamente.
- **Consecuencias:** el mantenimiento se reduce a revisar PRs desde el móvil; la fixture nueva se convierte en test.
- **Plan B:** si el Reparador acierta < 50 % de las veces, la PR solo adjunta la fixture y el error, sin diff.

## D-11 · Tres casos de aceptación, no uno

- **Contexto:** diseñar todo alrededor del MiniPC sobreajusta el Intérprete y el Extractor.
- **Decisión:** MiniPC (principal) + portátil 14" + router OpenWrt, en `app/ia/evaluacion/consultas.jsonl` y en los tests de contrato.
- **Consecuencias:** las claves de atributos se definen por categoría (`informatica`, `redes`, `genérica`).

## D-12 · Cierre por criterios, no por fechas

- **Decisión:** el proyecto termina cuando se cumplen los 9 criterios de [PLAN.md §2](PLAN.md#2-qué-significa-el-mejor-buscador-posible), verificados por workflows o por checklist en móvil real y anotados en la bitácora. No hay fechas objetivo: cada sesión cierra un hito de la [HOJA_DE_RUTA.md](HOJA_DE_RUTA.md).

## D-13 · La IA se consulta a través del gateway `apisor.oracle402.com`

- **Contexto:** el usuario indicó ese gateway para consultar agentes IA. El sandbox no puede alcanzarlo, así que no se ha podido inspeccionar su protocolo.
- **Decisión:** el SDK oficial de Anthropic se configura con `base_url = BP_IA_BASE_URL` (por defecto el gateway) y `auth_token = BP_IA_TOKEN` (Bearer) o `api_key = ANTHROPIC_API_KEY`. Se envía `fallbacks: "default"` (beta `server-side-fallback-2026-07-01`) y, si el gateway lo rechaza con 400/404, se reintenta sin él; se puede desactivar con `BP_IA_FALLBACKS=0`.
- **[SUPUESTO]** el gateway habla la API de Mensajes de Anthropic (`/v1/messages`) incluida la salida estructurada. **Plan B:** si es compatible con OpenAI u otro esquema, se añade un adaptador de transporte en `app/ia/` sin tocar los agentes.

## D-14 · El cosechador nocturno es el «navegador» del nivel C cuando no hay Firecrawl

- **Contexto:** `fuentes.yml` demostró que la mayoría de tiendas y comparadores españoles devuelven 403 anti-bot incluso a una única petición educada.
- **Decisión:** en vivo esas fuentes quedan en D (enlace); `cosechar.yml` las visita de noche con Chromium en el runner (robots y ritmo respetados), entrega el markdown al backend y el Extractor saca las ofertas, que se suman a la búsqueda original y la promocionan a C. Con `FIRECRAWL_API_KEY` el nivel C funciona también en vivo.
- **Consecuencias:** las búsquedas sobre esas fuentes se completan con horas de retraso; sigue sin haber evasión de bloqueos (si Chromium también recibe 403, la fuente se omite y queda registrado).

## D-15 · Keepa y Apify no se implementan por ahora

- **Contexto:** Keepa cuesta ≈ 19 €/mes (rompe el objetivo de ≤ 15 €) y ni Keepa ni Apify se pueden verificar sin clave.
- **Decisión:** quedan documentados en el catálogo como opcionales; Amazon se cubre por Google Shopping (Serper devuelve ofertas de Amazon.es) y por enlace directo. Se implementarán solo si el usuario decide pagarlos.

## D-16 · La verificación de la interfaz la hace Playwright en la sesión

- **Decisión:** la checklist de PLAN.md §12 se automatiza con un script de Playwright (Chromium preinstalado en el sandbox) contra el backend local y `docs/` servido por HTTP: 27 comprobaciones en móvil (390 px) y escritorio, sin errores de consola. Se repite en cada sesión que toque `docs/index.html`.
