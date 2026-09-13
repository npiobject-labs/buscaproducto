from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..bd import a_json, de_json
from . import Protegido, estado

router = APIRouter(tags=["informes"], dependencies=[Protegido])

REQUISITOS = {
    "24x7": "funcionamiento continuo 24/7 (consumo, temperaturas, fiabilidad a largo plazo)",
    "silencioso": "nivel de ruido en uso normal y bajo carga",
    "fiable": "fiabilidad y fallos conocidos",
}


async def _dominios_comunidad(st) -> list[str]:
    filas = await st.bd.todos("SELECT url FROM herramientas WHERE categoria = 'comunidades' AND activa = 1")
    from urllib.parse import urlsplit

    dominios = []
    for f in filas:
        d = urlsplit(f["url"]).netloc.lower().removeprefix("www.")
        if d and d not in dominios:
            dominios.append(d)
    return dominios


async def _producto(st, pid: int) -> dict[str, Any]:
    p = await st.bd.uno("SELECT * FROM productos WHERE id = ?", (pid,))
    if not p:
        raise HTTPException(404, {"error": "no_existe"})
    p["atributos"] = de_json(p.pop("atributos_json"), {})
    ofertas = await st.bd.todos(
        "SELECT o.id, o.precio, o.envio, o.url, h.nombre AS fuente_nombre FROM ofertas o JOIN herramientas h ON h.id = o.herramienta_id WHERE o.producto_id = ? AND o.precio IS NOT NULL ORDER BY o.precio + COALESCE(o.envio, 0)",
        (pid,),
    )
    p["ofertas"] = ofertas
    p["mejor_precio"] = (ofertas[0]["precio"] + (ofertas[0]["envio"] or 0)) if ofertas else None
    return p


@router.get("/productos/{pid}")
async def ver_producto(pid: int, st=Depends(estado)):
    return await _producto(st, pid)


@router.get("/productos/{pid}/informe")
async def ver_informe(pid: int, requisito: str = "24x7", st=Depends(estado)):
    p = await _producto(st, pid)
    fila = await st.bd.uno(
        "SELECT contenido_json, creado, modelo FROM informes WHERE tipo = 'investigacion' AND clave = ?",
        (_clave(st, p, requisito),),
    )
    if not fila:
        return {"producto_id": pid, "requisito": requisito, "informe": None}
    return {
        "producto_id": pid,
        "requisito": requisito,
        "informe": de_json(fila["contenido_json"]),
        "creado": fila["creado"],
        "modelo": fila["modelo"],
    }


def _clave(st, p: dict[str, Any], requisito: str) -> str:
    return (
        st.ia._clave("investigar", (p.get("nombre") or "").lower(), REQUISITOS.get(requisito, requisito))
        if st.ia
        else ""
    )


@router.post("/productos/{pid}/informe")
async def generar_informe(pid: int, requisito: str = "24x7", forzar: bool = False, st=Depends(estado)):
    if st.ia is None or not st.ia.disponible():
        raise HTTPException(503, {"error": "sin_ia", "detalle": "IA no configurada o presupuesto agotado"})
    p = await _producto(st, pid)
    informe = await st.ia.investigar(
        p, REQUISITOS.get(requisito, requisito), await _dominios_comunidad(st), forzar=forzar
    )
    if informe is None:
        raise HTTPException(502, {"error": "sin_informe", "detalle": "La IA no devolvió un informe válido"})
    if requisito == "24x7" and informe.veredicto in ("apto", "no_apto") and informe.confianza >= 0.6:
        at = {**p["atributos"], "apto_24_7": informe.veredicto == "apto", "apto_24_7_origen": "investigador"}
        await st.bd.ejecutar("UPDATE productos SET atributos_json = ? WHERE id = ?", (a_json(at), pid))
    return {"producto_id": pid, "requisito": requisito, "informe": informe.model_dump()}


class PeticionComparar(BaseModel):
    producto_ids: list[int]
    criterios: str = ""


@router.post("/comparar")
async def comparar(peticion: PeticionComparar, st=Depends(estado)):
    if not 2 <= len(peticion.producto_ids) <= 5:
        raise HTTPException(422, {"error": "cantidad", "detalle": "Compara entre 2 y 5 productos"})
    productos = [await _producto(st, pid) for pid in peticion.producto_ids]
    tabla = _tabla(productos)
    salida: dict[str, Any] = {"productos": productos, "tabla": tabla, "ia": None}
    if st.ia is not None and st.ia.disponible():
        resumidos = [
            {
                "id": p["id"],
                "nombre": p["nombre"],
                "atributos": p["atributos"],
                "mejor_precio": p["mejor_precio"],
                "n_ofertas": len(p["ofertas"]),
            }
            for p in productos
        ]
        try:
            comp = await st.ia.comparar(resumidos, peticion.criterios)
            salida["ia"] = comp.model_dump() if comp else None
        except Exception as e:  # noqa: BLE001
            salida["ia_error"] = f"{type(e).__name__}: {str(e)[:200]}"
    return salida


def _tabla(productos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from ..dominio import ATRIBUTOS

    claves: list[str] = []
    for p in productos:
        for k in p["atributos"]:
            if k in ATRIBUTOS and k not in claves:
                claves.append(k)
    filas = [
        {
            "atributo": "mejor_precio",
            "etiqueta": "Mejor precio (€)",
            "valores": {str(p["id"]): p["mejor_precio"] for p in productos},
        }
    ]
    for k in claves:
        filas.append(
            {
                "atributo": k,
                "etiqueta": ATRIBUTOS[k][0],
                "unidad": ATRIBUTOS[k][1],
                "valores": {str(p["id"]): p["atributos"].get(k) for p in productos},
            }
        )
    return filas
