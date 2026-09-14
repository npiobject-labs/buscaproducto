# Qué falta por hacer

Resumen operativo. Detalle largo en [HOJA_DE_RUTA.md](HOJA_DE_RUTA.md).

## 1. El único paso que desbloquea todo: `BP_CLAVE`

Sin esta clave la API responde 503, la web solo funciona en modo demo y los dos crons fallan cada día.

1. Genera una cadena larga al azar (por ejemplo en el móvil, cualquier gestor de contraseñas, 30+ caracteres).
2. **GitHub** → Settings → Secrets and variables → Actions → *New repository secret*: nombre `BP_CLAVE`, valor esa cadena.
3. **GitHub** → Actions → *Desplegar backend en Fly.io* → *Run workflow* (los secretos se pasan a Fly durante el despliegue; si no redespliegas, no llegan).
4. Abre la web → pestaña **Estado** → pega la misma clave → *Guardar y conectar*. Debe poner «conectado».

A partir de aquí la app ya busca de verdad, en modo enlace, y las alertas y la cosecha dejan de fallar.

## 2. Claves que hay que conseguir

Todas se crean igual: **GitHub** → Settings → Secrets and variables → Actions → *New repository secret*. Después, **un despliegue** (paso 1.3) para que lleguen a Fly. Sin una clave, su fuente sigue funcionando como enlace y queda anotado en la pestaña Estado.

| Secreto | Dónde se consigue | Coste | Para qué |
|---|---|---|---|
| `BP_CLAVE` | la generas tú | — | **Imprescindible.** Protege la API |
| `BP_IA_TOKEN` | tu gateway `apisor.oracle402.com` | según tu acuerdo | Los seis agentes de IA. Alternativa: `ANTHROPIC_API_KEY` de console.anthropic.com más la variable `BP_IA_BASE_URL` con `https://api.anthropic.com` |
| `SERPER_API_KEY` | serper.dev | 2.500 búsquedas gratis, luego ≈ 1 $/1.000 | Google Shopping (incluye ofertas de Amazon) |
| `EBAY_CLIENT_ID` y `EBAY_CLIENT_SECRET` | developer.ebay.com → *Application keys* (producción) | gratis | eBay, nuevo y segunda mano |
| `FIRECRAWL_API_KEY` | firecrawl.dev | 500 páginas gratis | Tiendas que bloquean peticiones directas (Idealo, PcComponentes, Geizhals…) |
| `TELEGRAM_BOT_TOKEN` y `TELEGRAM_CHAT_ID` | @BotFather y @userinfobot en Telegram | gratis | Avisos de precio en el móvil |
| `KEEPA_API_KEY` | keepa.com | ≈ 19 €/mes | Opcional. Amazon con histórico. Sin decidir (D-15) |
| `APIFY_TOKEN` | apify.com | crédito gratis | Opcional. Fuentes que fallen con lo anterior |

**Orden recomendado:** `BP_CLAVE` → `BP_IA_TOKEN` → `SERPER_API_KEY` → `TELEGRAM_*` → el resto.

## 3. Operaciones por servicio

### GitHub
- Crear los secretos de arriba y relanzar el despliegue (paso 1).
- Nada más es obligatorio. Pages y Fly ya despliegan solos en cada push a `main`.
- Opcional: los crons de vigilancia y cosecha fallan a diario mientras falte `BP_CLAVE`. Se puede cambiar para que terminen en verde con un aviso.

### Fly.io
- **Nada manual.** El despliegue crea la app, el volumen de datos y pasa los secretos.
- El gasto se vigila solo: `vigilancia-fly.yml` avisa cada lunes si alguna máquina se queda encendida.
- Solo si quieres mirarlo: https://fly.io/apps/buscaproducto-npiobject-labs

### Google Drive
- **Nada.** La carpeta `Mi unidad/buscaproducto` de `fsantagonza@gmail.com` ya recibe las copias.
- Pendiente menor: la carpeta antigua en la otra cuenta (`zambron@gmail.com`) quedó huérfana; bórrala cuando quieras, no se usa.

## 4. Trabajo que queda, por orden

1. Probar la web en el móvil e instalarla («Añadir a pantalla de inicio»).
2. Con `BP_CLAVE` puesta: buscar el caso MiniPC y comprobar que salen enlaces por fuente.
3. Con las claves de IA y Serper: comprobar que la interpretación entiende la consulta y que llegan ofertas con precio.
4. Sesión de cierre: medir los cuatro criterios que aún no se pueden medir sin claves (entrada natural, cobertura de fuentes, requisitos como «24/7», alertas).
5. Decidir si se paga Keepa para cubrir Amazon con histórico.
6. Corregir las URL de búsqueda marcadas «(verificar)» en el catálogo, con lo que reporte el workflow de fuentes.
