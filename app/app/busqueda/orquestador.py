"""Ciclo de vida de una búsqueda: crear → consultar fuentes en paralelo → normalizar → puntuar → agrupar."""

from __future__ import annotations

import asyncio
import secrets
import time
from typing import Any

import httpx

from ..bd import BD, a_json, ahora, de_json
from ..config import config
from ..dominio import ATRIBUTOS_BLANDOS, Consulta, Especificacion, OfertaCruda, PeticionBusqueda
from ..fuentes import Contexto, adaptador_para, registro
from ..http import Bloqueado, Http
from .agrupar import agrupar, clave_canonica
from .atributos import extraer, formato_desde_texto
from .normalizar import hash_oferta, limpiar_titulo, normalizar_estado, url_canonica
from .puntuar import puntuar

TAREAS: dict[str, asyncio.Task] = {}


async def herramientas_disponibles(bd: BD, slugs: list[str] | None) -> list[dict[str, Any]]:
    filas = await bd.todos("SELECT * FROM herramientas WHERE activa = 1 ORDER BY categoria, nombre")
    salida = []
    for h in filas:
        if slugs is not None and h["slug"] not in slugs:
            continue
        if adaptador_para(h) is None:
            continue
        if h["categoria"] in ("infraestructura", "apis_scraping") and h["slug"] not in registro():
            continue
        salida.append(h)
    return salida


async def crear(bd: BD, peticion: PeticionBusqueda, ia: Any = None) -> tuple[str, dict[str, Any] | None]:
    interpretacion: dict[str, Any] | None = None
    specs = list(peticion.especificaciones)
    texto = (peticion.texto or "").strip()
    precio_min, precio_max, estado = peticion.precio_min, peticion.precio_max, peticion.estado
    consulta_base = texto
    if texto and peticion.interpretar and ia is not None and ia.disponible():
        try:
            inter = await ia.interpretar(texto)
        except Exception as e:  # la IA nunca bloquea una búsqueda
            await bd.evento("fallo del Intérprete", "ia", "aviso", error=str(e)[:300])
            inter = None
        if inter is not None:
            interpretacion = inter.model_dump()
            claves = {s.clave for s in specs}
            specs += [s for s in inter.especificaciones if s.clave not in claves]
            precio_min = precio_min if precio_min is not None else inter.precio_min
            precio_max = precio_max if precio_max is not None else inter.precio_max
            if estado == "cualquiera":
                estado = inter.estado
            consulta_base = inter.consulta_base or texto
    for s in specs:
        if s.clave in ATRIBUTOS_BLANDOS:
            s.blando = True
    if not consulta_base:
        consulta_base = " ".join(f"{s.clave} {s.valor}" for s in specs[:3]) or "producto"
    bid = secrets.token_urlsafe(8)
    fuentes = await herramientas_disponibles(bd, peticion.fuentes)
    await bd.ejecutar(
        "INSERT INTO busquedas (id, texto, especificaciones_json, precio_min, precio_max, estado_producto, fuentes_json, estado, interpretacion_json, creada) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            bid,
            texto,
            a_json([s.model_dump() for s in specs]),
            precio_min,
            precio_max,
            estado,
            a_json([h["slug"] for h in fuentes]),
            "pendiente",
            a_json(
                {
                    **(interpretacion or {}),
                    "consulta_base": consulta_base,
                    "mostrar_fuera_rango": peticion.mostrar_fuera_rango,
                    "usar_cache": peticion.usar_cache,
                }
            ),
            ahora(),
        ),
        commit=False,
    )
    for h in fuentes:
        await bd.ejecutar(
            "INSERT INTO busqueda_fuentes (busqueda_id, herramienta_id, slug, estado) VALUES (?,?,?,?)",
            (bid, h["id"], h["slug"], "pendiente"),
            commit=False,
        )
    await bd.c.commit()
    return bid, interpretacion


def lanzar(bd: BD, http: Http, bid: str, ia: Any = None) -> asyncio.Task:
    tarea = asyncio.create_task(ejecutar(bd, http, bid, ia))
    TAREAS[bid] = tarea
    tarea.add_done_callback(lambda t: TAREAS.pop(bid, None))
    return tarea


async def ejecutar(bd: BD, http: Http, bid: str, ia: Any = None) -> None:
    b = await bd.uno("SELECT * FROM busquedas WHERE id = ?", (bid,))
    if not b:
        return
    await bd.ejecutar("UPDATE busquedas SET estado = 'en_curso' WHERE id = ?", (bid,))
    specs = [Especificacion(**s) for s in de_json(b["especificaciones_json"], [])]
    inter = de_json(b["interpretacion_json"], {}) or {}
    consulta = Consulta(
        texto=inter.get("consulta_base") or b["texto"] or "",
        especificaciones=specs,
        precio_min=b["precio_min"],
        precio_max=b["precio_max"],
        estado=b["estado_producto"],
    )
    consultas_por_fuente = inter.get("consultas_por_fuente") or {}
    fuentes = await bd.todos(
        "SELECT h.* FROM busqueda_fuentes bf JOIN herramientas h ON h.id = bf.herramienta_id WHERE bf.busqueda_id = ?",
        (bid,),
    )
    semaforo = asyncio.Semaphore(config.fuentes_paralelas)

    async def una(h: dict[str, Any]) -> None:
        async with semaforo:
            c = consulta.model_copy(update={"texto": consultas_por_fuente.get(h["slug"], consulta.texto)})
            try:
                await consultar_fuente(bd, http, ia, bid, h, c, inter.get("usar_cache", True))
            except Exception as e:  # noqa: BLE001 - una fuente nunca tumba la búsqueda
                await bd.evento(
                    "fallo inesperado al guardar la fuente", h["slug"], "error", error=repr(e)[:400]
                )
                await bd.ejecutar(
                    "UPDATE busqueda_fuentes SET estado = 'error', error = ? WHERE busqueda_id = ? AND herramienta_id = ?",
                    (f"{type(e).__name__}: {str(e)[:200]}", bid, h["id"]),
                )

    try:
        try:
            await asyncio.wait_for(
                asyncio.gather(*(una(h) for h in fuentes)), timeout=config.timeout_busqueda_s
            )
        except TimeoutError:
            await bd.ejecutar(
                "UPDATE busqueda_fuentes SET estado = 'error', error = 'tiempo agotado' WHERE busqueda_id = ? AND estado IN ('pendiente','en_curso')",
                (bid,),
            )
        await enriquecer_con_ia(bd, ia, bid, specs)
        await reagrupar(bd, bid, ia)
        await bd.ejecutar(
            "UPDATE busquedas SET estado = 'terminada', terminada = ? WHERE id = ?", (ahora(), bid)
        )
    except Exception as e:
        await bd.evento("fallo al cerrar la búsqueda", "busqueda", "error", error=repr(e)[:400], busqueda=bid)
        await bd.ejecutar(
            "UPDATE busquedas SET estado = 'error', error = ?, terminada = ? WHERE id = ?",
            (repr(e)[:400], ahora(), bid),
        )


async def consultar_fuente(
    bd: BD, http: Http, ia: Any, bid: str, h: dict[str, Any], consulta: Consulta, usar_cache: bool = True
) -> None:
    adaptador = adaptador_para(h)
    inicio = time.monotonic()
    await bd.ejecutar(
        "UPDATE busqueda_fuentes SET estado = 'en_curso' WHERE busqueda_id = ? AND herramienta_id = ?",
        (bid, h["id"]),
    )
    ctx = Contexto(bd=bd, http=http, herramienta=h, ia=ia, config={"usar_cache": usar_cache})
    estado, error, nivel_usado, desde_cache = "ok", None, adaptador.nivel if adaptador else "D", 0
    ofertas: list[OfertaCruda] = []
    try:
        if adaptador is None:
            raise Bloqueado("sin adaptador")
        ok, motivo = adaptador.disponible(ctx)
        if not ok:
            await bd.evento(f"fuente omitida: {motivo}", h["slug"], "info")
            adaptador = registro().get("enlace") if h.get("url_plantilla_busqueda") else None
            estado, error = ("degradada", motivo) if adaptador else ("omitida", motivo)
            nivel_usado = "D"
        if adaptador is not None:
            ofertas = await asyncio.wait_for(
                adaptador.buscar(consulta, ctx), timeout=config.timeout_fuente_s + 5
            )
            desde_cache = int(ctx.config.get("desde_cache", 0))
    except (Bloqueado, httpx.HTTPError, TimeoutError, ValueError) as e:
        motivo = f"{type(e).__name__}: {str(e)[:200]}"
        enlace = registro().get("enlace")
        if h.get("url_plantilla_busqueda") and enlace is not None and nivel_usado != "D":
            ofertas = await enlace.buscar(consulta, ctx)
            estado, error, nivel_usado = "degradada", motivo, "D"
        else:
            estado, error = "error", motivo
    except Exception as e:  # noqa: BLE001 - un adaptador roto no tumba la búsqueda
        estado, error = "error", f"{type(e).__name__}: {str(e)[:200]}"
        await bd.evento("excepción en adaptador", h["slug"], "error", error=repr(e)[:400])
    n = await guardar_ofertas(bd, bid, h, ofertas, consulta)
    ms = int((time.monotonic() - inicio) * 1000)
    await bd.ejecutar(
        "UPDATE busqueda_fuentes SET estado = ?, n_ofertas = ?, error = ?, ms = ?, desde_cache = ?, nivel_usado = ? WHERE busqueda_id = ? AND herramienta_id = ?",
        (estado, n, error, ms, desde_cache, nivel_usado, bid, h["id"]),
    )
    await bd.ejecutar(
        "INSERT INTO fuente_stats (slug, fecha, n_ofertas, estado) VALUES (?,?,?,?)",
        (h["slug"], ahora(), n, estado),
    )
    if estado == "ok" and nivel_usado == "C" and n > 0 and not h.get("universal_ok"):
        await bd.ejecutar(
            "UPDATE herramientas SET universal_ok = 1, nivel = CASE WHEN nivel = 'D' THEN 'C' ELSE nivel END WHERE id = ?",
            (h["id"],),
        )
        await bd.evento("promocionada a nivel C", h["slug"], "info")


async def guardar_ofertas(
    bd: BD, bid: str, h: dict[str, Any], ofertas: list[OfertaCruda], consulta: Consulta
) -> int:
    n = 0
    formato = formato_desde_texto(consulta.texto)
    for pos, o in enumerate(ofertas):
        if not o.url or not o.titulo:
            continue
        titulo = limpiar_titulo(o.titulo)
        h_of = hash_oferta(h["id"], o.url)
        if o.tipo == "enlace":
            existente = await bd.uno("SELECT id FROM ofertas WHERE hash = ?", (h_of,))
            if existente:
                oid = existente["id"]
                await bd.ejecutar(
                    "UPDATE ofertas SET ultima_vez = ?, titulo = ? WHERE id = ?",
                    (ahora(), titulo, oid),
                    commit=False,
                )
            else:
                oid = await bd.ejecutar(
                    "INSERT INTO ofertas (herramienta_id, url, titulo, tipo, hash, primera_vez, ultima_vez) VALUES (?,?,?,?,?,?,?)",
                    (h["id"], o.url, titulo, "enlace", h_of, ahora(), ahora()),
                    commit=False,
                )
            await bd.ejecutar(
                "INSERT OR REPLACE INTO busqueda_ofertas (busqueda_id, oferta_id, puntuacion, explicacion_json, posicion) VALUES (?,?,?,?,?)",
                (bid, oid, 0, "[]", pos),
                commit=False,
            )
            n += 1
            continue
        atributos = {
            **extraer(titulo, o.texto_extra),
            **{k: v for k, v in o.atributos.items() if v not in (None, "")},
        }
        if formato and "formato" not in atributos:
            atributos["formato"] = formato
        estado_producto = normalizar_estado(o.estado_producto)
        if consulta.estado != "cualquiera" and estado_producto not in ("desconocido", consulta.estado):
            continue
        if o.moneda and o.moneda.upper() not in ("EUR", "€"):
            atributos["moneda_original"] = o.moneda
        puntuacion, explicacion = puntuar(consulta.especificaciones, atributos, titulo)
        clave = clave_canonica(titulo, atributos.get("marca"), atributos.get("modelo"), o.ean, o.asin)
        producto = await bd.uno("SELECT id, atributos_json FROM productos WHERE clave_canonica = ?", (clave,))
        if producto:
            pid = producto["id"]
            fusion = {**de_json(producto["atributos_json"], {}), **atributos}
            await bd.ejecutar(
                "UPDATE productos SET atributos_json = ?, actualizado = ?, imagen_url = COALESCE(imagen_url, ?) WHERE id = ?",
                (a_json(fusion), ahora(), o.imagen_url, pid),
                commit=False,
            )
        else:
            # INSERT OR IGNORE: otra fuente puede haber creado el mismo producto en paralelo.
            await bd.ejecutar(
                "INSERT OR IGNORE INTO productos (clave_canonica, nombre, marca, modelo, categoria, atributos_json, imagen_url, actualizado) VALUES (?,?,?,?,?,?,?,?)",
                (
                    clave,
                    titulo,
                    atributos.get("marca"),
                    atributos.get("modelo"),
                    formato,
                    a_json(atributos),
                    o.imagen_url,
                    ahora(),
                ),
                commit=False,
            )
            pid = (await bd.uno("SELECT id FROM productos WHERE clave_canonica = ?", (clave,)))["id"]
        existente = await bd.uno("SELECT id, precio, envio FROM ofertas WHERE hash = ?", (h_of,))
        if existente:
            oid = existente["id"]
            await bd.ejecutar(
                "UPDATE ofertas SET producto_id = ?, titulo = ?, precio = ?, envio = ?, moneda = ?, estado_producto = ?, disponibilidad = ?, vendedor = ?, valoracion = ?, n_valoraciones = ?, imagen_url = COALESCE(?, imagen_url), atributos_json = ?, ultima_vez = ? WHERE id = ?",
                (
                    pid,
                    titulo,
                    o.precio,
                    o.envio,
                    o.moneda or "EUR",
                    estado_producto,
                    o.disponibilidad,
                    o.vendedor,
                    o.valoracion,
                    o.n_valoraciones,
                    o.imagen_url,
                    a_json(atributos),
                    ahora(),
                    oid,
                ),
                commit=False,
            )
            if o.precio is not None and (
                existente["precio"] != o.precio or (existente["envio"] or 0) != (o.envio or 0)
            ):
                await bd.ejecutar(
                    "INSERT INTO precios (oferta_id, fecha, precio, envio) VALUES (?,?,?,?)",
                    (oid, ahora(), o.precio, o.envio),
                    commit=False,
                )
        else:
            oid = await bd.ejecutar(
                "INSERT INTO ofertas (producto_id, herramienta_id, url, titulo, precio, envio, moneda, estado_producto, disponibilidad, vendedor, valoracion, n_valoraciones, imagen_url, atributos_json, hash, primera_vez, ultima_vez, tipo) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'oferta')",
                (
                    pid,
                    h["id"],
                    url_canonica(o.url),
                    titulo,
                    o.precio,
                    o.envio,
                    o.moneda or "EUR",
                    estado_producto,
                    o.disponibilidad,
                    o.vendedor,
                    o.valoracion,
                    o.n_valoraciones,
                    o.imagen_url,
                    a_json(atributos),
                    h_of,
                    ahora(),
                    ahora(),
                ),
                commit=False,
            )
            if o.precio is not None:
                await bd.ejecutar(
                    "INSERT INTO precios (oferta_id, fecha, precio, envio) VALUES (?,?,?,?)",
                    (oid, ahora(), o.precio, o.envio),
                    commit=False,
                )
        await bd.ejecutar(
            "INSERT OR REPLACE INTO busqueda_ofertas (busqueda_id, oferta_id, puntuacion, explicacion_json, posicion) VALUES (?,?,?,?,?)",
            (bid, oid, puntuacion, a_json(explicacion), pos),
            commit=False,
        )
        n += 1
    await bd.c.commit()
    return n


async def enriquecer_con_ia(bd: BD, ia: Any, bid: str, specs: list[Especificacion]) -> None:
    """Pide al Extractor los atributos que faltan en las ofertas para las claves pedidas."""
    if ia is None or not ia.disponible() or not specs:
        return
    claves = [s.clave for s in specs if s.clave not in ATRIBUTOS_BLANDOS]
    if not claves:
        return
    filas = await bd.todos(
        "SELECT o.id, o.titulo, o.atributos_json, o.producto_id FROM busqueda_ofertas bo JOIN ofertas o ON o.id = bo.oferta_id WHERE bo.busqueda_id = ? AND o.tipo = 'oferta'",
        (bid,),
    )
    pendientes = [f for f in filas if any(k not in de_json(f["atributos_json"], {}) for k in claves)]
    if not pendientes:
        return
    try:
        extraidos = await ia.extraer_atributos([(f["id"], f["titulo"]) for f in pendientes[:80]], claves)
    except Exception as e:
        await bd.evento("fallo del Extractor", "ia", "aviso", error=str(e)[:300])
        return
    for f in pendientes:
        nuevos = extraidos.get(f["id"]) or {}
        if not nuevos:
            continue
        atributos = {**nuevos, **de_json(f["atributos_json"], {})}  # lo extraído por reglas manda
        puntuacion, explicacion = puntuar(specs, atributos, f["titulo"])
        await bd.ejecutar(
            "UPDATE ofertas SET atributos_json = ? WHERE id = ?", (a_json(atributos), f["id"]), commit=False
        )
        await bd.ejecutar(
            "UPDATE busqueda_ofertas SET puntuacion = ?, explicacion_json = ? WHERE busqueda_id = ? AND oferta_id = ?",
            (puntuacion, a_json(explicacion), bid, f["id"]),
            commit=False,
        )
        if f["producto_id"]:
            p = await bd.uno("SELECT atributos_json FROM productos WHERE id = ?", (f["producto_id"],))
            if p:
                await bd.ejecutar(
                    "UPDATE productos SET atributos_json = ? WHERE id = ?",
                    (a_json({**nuevos, **de_json(p["atributos_json"], {})}), f["producto_id"]),
                    commit=False,
                )
    await bd.c.commit()


async def reagrupar(bd: BD, bid: str, ia: Any = None) -> None:
    """Segunda pasada de dedupe por similitud de títulos entre las ofertas de la búsqueda."""
    filas = await bd.todos(
        "SELECT o.id, o.titulo, o.producto_id, p.clave_canonica FROM busqueda_ofertas bo JOIN ofertas o ON o.id = bo.oferta_id LEFT JOIN productos p ON p.id = o.producto_id WHERE bo.busqueda_id = ? AND o.tipo = 'oferta'",
        (bid,),
    )
    if len(filas) < 2:
        return
    exactas = [
        (
            f["id"],
            f["titulo"],
            f["clave_canonica"] if (f["clave_canonica"] or "").split(":")[0] in ("ean", "asin", "mm") else "",
        )
        for f in filas
    ]
    grupos, dudosas = agrupar(exactas)
    if dudosas and ia is not None and ia.disponible():
        try:
            titulos = {f["id"]: f["titulo"] for f in filas}
            iguales = await ia.juzgar_duplicados([(a, titulos[a], b, titulos[b]) for a, b, _ in dudosas[:30]])
            for a, b in iguales:
                grupos[a] = grupos.get(b, b)
        except Exception as e:
            await bd.evento("fallo del juez de duplicados", "ia", "aviso", error=str(e)[:300])
    producto_de = {f["id"]: f["producto_id"] for f in filas}
    for oid, rep in grupos.items():
        if oid != rep and producto_de.get(oid) != producto_de.get(rep) and producto_de.get(rep):
            await bd.ejecutar(
                "UPDATE ofertas SET producto_id = ? WHERE id = ?", (producto_de[rep], oid), commit=False
            )
    await bd.c.commit()
