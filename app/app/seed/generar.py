"""Genera herramientas.json a partir de docs/planificacion/CATALOGO_HERRAMIENTAS.md.

Uso: python -m app.seed.generar [--comprobar]
Con --comprobar no escribe: falla (código 1) si el JSON del repo difiere del catálogo.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
CATALOGO = AQUI.parents[2] / "docs" / "planificacion" / "CATALOGO_HERRAMIENTAS.md"
SALIDA = AQUI / "herramientas.json"

CATEGORIAS = {
    "1": "comparadores",
    "2": "tiendas",
    "3": "historico",
    "4": "asistentes_ia",
    "5": "apis_scraping",
    "6": "comunidades",
    "7": "infraestructura",
}


def _limpiar(celda: str) -> str:
    return re.sub(r"\s+", " ", celda.replace("`", "")).strip()


def _plantilla(celda: str) -> tuple[str | None, bool]:
    celda = _limpiar(celda)
    if celda in ("", "—", "-"):
        return None, False
    verificar = "(verificar)" in celda
    url = celda.replace("(verificar)", "").strip()
    return (url if "{q}" in url else None), verificar


def _nivel(celda: str) -> str:
    celda = _limpiar(celda)
    m = re.match(r"([ABCD])", celda)
    return m.group(1) if m else "-"


def parsear(md: str) -> list[dict]:
    herramientas: list[dict] = []
    categoria = None
    cabecera: list[str] | None = None
    for linea in md.splitlines():
        m = re.match(r"^## (\d)\.", linea)
        if m:
            categoria = CATEGORIAS[m.group(1)]
            cabecera = None
            continue
        if linea.startswith("## ") or linea.startswith("---"):
            categoria = None
            continue
        if not categoria or not linea.startswith("|"):
            continue
        celdas = [c for c in linea.strip().strip("|").split("|")]
        if cabecera is None:
            cabecera = [_limpiar(c).lower() for c in celdas]
            continue
        if set(_limpiar(c) for c in celdas) <= {"---", ""}:
            continue
        fila = dict(zip(cabecera, celdas, strict=False))
        slug = _limpiar(fila.get("slug", ""))
        if not slug:
            continue
        plantilla, verificar = _plantilla(fila.get("url_plantilla_busqueda", ""))
        nivel = _nivel(fila.get("nivel", "-"))
        notas = _limpiar(fila.get("notas", "") or fila.get("uso en la app", "") or fila.get("uso", ""))
        herramientas.append(
            {
                "slug": slug,
                "nombre": _limpiar(fila.get("nombre", slug)),
                "categoria": categoria,
                "url": _limpiar(fila.get("url", "")),
                "url_plantilla_busqueda": plantilla,
                "plantilla_por_verificar": verificar,
                "tipo_acceso": _limpiar(fila.get("tipo", "") or fila.get("tipo_acceso", "")),
                "coste": _limpiar(fila.get("coste", "")),
                "descripcion": notas,
                "nivel": nivel if nivel != "-" else "D",
                "participa": nivel != "-" and (plantilla is not None or nivel in "AB"),
                "politica_scraping": _limpiar(fila.get("politica", "") or fila.get("politica_scraping", "")),
                "fase": _limpiar(fila.get("fase", "")),
            }
        )
    return herramientas


def generar() -> str:
    datos = parsear(CATALOGO.read_text(encoding="utf-8"))
    return json.dumps(datos, ensure_ascii=False, indent=1) + "\n"


def main(argv: list[str]) -> int:
    contenido = generar()
    if "--comprobar" in argv:
        actual = SALIDA.read_text(encoding="utf-8") if SALIDA.exists() else ""
        if actual != contenido:
            print(
                "herramientas.json no coincide con el catálogo: ejecuta python -m app.seed.generar",
                file=sys.stderr,
            )
            return 1
        print("seed al día")
        return 0
    SALIDA.write_text(contenido, encoding="utf-8")
    print(f"{len(json.loads(contenido))} herramientas → {SALIDA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
