from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ..bd import a_json, ahora, de_json
from ..dominio import Consulta, HerramientaEntrada
from ..fuentes import Contexto, adaptador_para, registro
from . import Protegido, estado

router = APIRouter(prefix="/herramientas", tags=["herramientas"], dependencies=[Protegido])


def _publica(h: dict[str, Any]) -> dict[str, Any]:
    adaptador = adaptador_para(h)
    h = dict(h)
    h["activa"] = bool(h["activa"])
    h["necesita_js"] = bool(h["necesita_js"])
    h["universal_ok"] = bool(h["universal_ok"])
    h["config"] = de_json(h.pop("config_json"), {}) or {}
    h["participa"] = adaptador is not None
    h["nivel_actual"] = adaptador.nivel if adaptador else None
    h["adaptador_actual"] = adaptador.slug if adaptador else None
    return h


@router.get("")
async def listar(st=Depends(estado)):
    filas = await st.bd.todos("SELECT * FROM herramientas ORDER BY categoria, nombre")
    salida = []
    for h in filas:
        p = _publica(h)
        adaptador = adaptador_para(h)
        if adaptador is not None:
            ok, motivo = adaptador.disponible(Contexto(bd=st.bd, http=st.http, herramienta=h, ia=st.ia))
            p["disponible"], p["motivo"] = ok, motivo
        salida.append(p)
    return {"herramientas": salida, "adaptadores": sorted(registro())}


@router.post("", status_code=201)
async def crear(entrada: HerramientaEntrada, st=Depends(estado)):
    slug = _slug(entrada.nombre)
    if await st.bd.uno("SELECT 1 FROM herramientas WHERE slug = ?", (slug,)):
        raise HTTPException(
            409, {"error": "duplicada", "detalle": f"Ya existe una herramienta con slug {slug}"}
        )
    hid = await st.bd.ejecutar(
        "INSERT INTO herramientas (slug, nombre, categoria, url, url_plantilla_busqueda, tipo_acceso, coste, descripcion, origen, activa, nivel, politica_scraping, necesita_js, creada, actualizada) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            slug,
            entrada.nombre,
            entrada.categoria,
            entrada.url,
            entrada.url_plantilla_busqueda,
            entrada.tipo_acceso,
            entrada.coste,
            entrada.descripcion,
            "usuario",
            int(entrada.activa),
            "D",
            "verificar robots",
            int(entrada.necesita_js),
            ahora(),
            ahora(),
        ),
    )
    return _publica(await st.bd.uno("SELECT * FROM herramientas WHERE id = ?", (hid,)))


@router.put("/{hid}")
async def editar(hid: int, entrada: HerramientaEntrada, st=Depends(estado)):
    h = await st.bd.uno("SELECT * FROM herramientas WHERE id = ?", (hid,))
    if not h:
        raise HTTPException(404, {"error": "no_existe"})
    if h["origen"] != "usuario":
        raise HTTPException(
            403, {"error": "predefinida", "detalle": "Las predefinidas solo se activan o desactivan"}
        )
    await st.bd.ejecutar(
        "UPDATE herramientas SET nombre=?, categoria=?, url=?, url_plantilla_busqueda=?, tipo_acceso=?, coste=?, descripcion=?, activa=?, necesita_js=?, actualizada=? WHERE id=?",
        (
            entrada.nombre,
            entrada.categoria,
            entrada.url,
            entrada.url_plantilla_busqueda,
            entrada.tipo_acceso,
            entrada.coste,
            entrada.descripcion,
            int(entrada.activa),
            int(entrada.necesita_js),
            ahora(),
            hid,
        ),
    )
    return _publica(await st.bd.uno("SELECT * FROM herramientas WHERE id = ?", (hid,)))


@router.patch("/{hid}/activa")
async def activar(hid: int, cuerpo: dict[str, Any], st=Depends(estado)):
    if not await st.bd.uno("SELECT 1 FROM herramientas WHERE id = ?", (hid,)):
        raise HTTPException(404, {"error": "no_existe"})
    await st.bd.ejecutar(
        "UPDATE herramientas SET activa = ?, actualizada = ? WHERE id = ?",
        (int(bool(cuerpo.get("activa", True))), ahora(), hid),
    )
    return _publica(await st.bd.uno("SELECT * FROM herramientas WHERE id = ?", (hid,)))


@router.delete("/{hid}", status_code=204)
async def borrar(hid: int, st=Depends(estado)):
    h = await st.bd.uno("SELECT origen FROM herramientas WHERE id = ?", (hid,))
    if not h:
        raise HTTPException(404, {"error": "no_existe"})
    if h["origen"] != "usuario":
        raise HTTPException(
            403, {"error": "predefinida", "detalle": "Las predefinidas no se borran; desactívalas"}
        )
    await st.bd.ejecutar("DELETE FROM herramientas WHERE id = ?", (hid,))


@router.post("/{hid}/probar")
async def probar(hid: int, cuerpo: dict[str, Any] | None = None, st=Depends(estado)):
    """Lanza la consulta de prueba solo en esta fuente y devuelve el nivel alcanzado y una muestra."""
    h = await st.bd.uno("SELECT * FROM herramientas WHERE id = ?", (hid,))
    if not h:
        raise HTTPException(404, {"error": "no_existe"})
    adaptador = adaptador_para(h)
    if adaptador is None:
        return {"nivel": None, "ok": False, "motivo": "sin plantilla de búsqueda ni adaptador", "muestra": []}
    texto = (cuerpo or {}).get("texto") or "mini pc 16gb"
    ctx = Contexto(bd=st.bd, http=st.http, herramienta=h, ia=st.ia, config={"usar_cache": False})
    ok, motivo = adaptador.disponible(ctx)
    if not ok:
        return {
            "nivel": "D" if h.get("url_plantilla_busqueda") else None,
            "ok": False,
            "motivo": motivo,
            "muestra": [],
        }
    try:
        ofertas = await adaptador.buscar(Consulta(texto=texto), ctx)
    except Exception as e:  # noqa: BLE001
        return {
            "nivel": adaptador.nivel,
            "ok": False,
            "motivo": f"{type(e).__name__}: {str(e)[:200]}",
            "muestra": [],
        }
    reales = [o for o in ofertas if o.tipo == "oferta"]
    if adaptador.nivel == "C" and reales and not h["universal_ok"]:
        await st.bd.ejecutar(
            "UPDATE herramientas SET universal_ok = 1, nivel = 'C', actualizada = ? WHERE id = ?",
            (ahora(), hid),
        )
    return {
        "nivel": adaptador.nivel,
        "ok": bool(ofertas),
        "motivo": "" if ofertas else "0 resultados",
        "n": len(ofertas),
        "muestra": [o.model_dump() for o in ofertas[:3]],
    }


def _slug(nombre: str) -> str:
    import re
    import unicodedata

    t = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:60] or "herramienta"


__all__ = ["router", "a_json"]
