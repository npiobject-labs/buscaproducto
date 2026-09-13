import pytest

from app.busqueda.agrupar import agrupar, clave_canonica, similitud
from app.busqueda.atributos import extraer, formato_desde_texto
from app.busqueda.normalizar import normalizar_estado, parsear_precio, url_canonica
from app.busqueda.puntuar import puntuar
from app.dominio import Especificacion


@pytest.mark.parametrize(
    "texto,esperado",
    [
        ("1.299,00 €", 1299.0),
        ("299.99", 299.99),
        ("1,299.00", 1299.0),
        ("129 €", 129.0),
        ("EUR 1.299", 1299.0),
        ("249,9", 249.9),
        ("", None),
        ("gratis", None),
        (149, 149.0),
    ],
)
def test_parsear_precio(texto, esperado):
    assert parsear_precio(texto) == esperado


def test_estado():
    assert normalizar_estado("Reacondicionado - Como nuevo") == "reacondicionado"
    assert normalizar_estado("Used") == "segunda_mano"
    assert normalizar_estado("Brand New") == "nuevo"
    assert normalizar_estado(None) == "desconocido"


def test_url_canonica():
    assert url_canonica("https://Tienda.es/p/1/?utm_source=x&b=2&a=1") == "https://tienda.es/p/1?a=1&b=2"


def test_extraer_atributos():
    a = extraer("Beelink Mini S12 Pro Mini PC Intel N100 16GB DDR4 500GB SSD WiFi 6 Windows 11 Pro")
    assert a["ram_gb"] == 16 and a["almacenamiento_gb"] == 500 and a["marca"] == "Beelink"
    assert a["cpu"].upper().startswith("INTEL N100") or "N100" in a["cpu"]
    b = extraer("GMKtec NucBox G3 Plus, 16GB+1TB, fanless, 12W TDP")
    assert (
        b["ram_gb"] == 16
        and b["almacenamiento_gb"] == 1024
        and b["fanless"] is True
        and b["tdp_w"] == 12
        and b["apto_24_7"] is True
    )
    c = extraer('Portátil ASUS Vivobook 14" FHD 8GB RAM 256GB SSD')
    assert c["pantalla_pulgadas"] == 14 and c["ram_gb"] == 8 and c["almacenamiento_gb"] == 256
    assert formato_desde_texto("mini pc 8gb") == "minipc" and formato_desde_texto("router wifi 6") == "router"


def test_puntuar_explica():
    specs = [
        Especificacion(clave="ram_gb", operador=">=", valor=8),
        Especificacion(clave="almacenamiento_gb", operador=">=", valor=500),
        Especificacion(clave="apto_24_7", operador="=", valor=True, blando=True),
    ]
    p, ex = puntuar(specs, {"ram_gb": 16, "almacenamiento_gb": 512}, "x")
    assert p == pytest.approx(100 * (1 + 1 + 0.5) / 3, abs=0.1)
    assert [e["cumple"] for e in ex] == [True, True, False] and ex[2]["conocido"] is False
    p2, _ = puntuar(
        specs,
        {"ram_gb": 4, "almacenamiento_gb": 256, "apto_24_7": True, "apto_24_7_origen": "heuristica"},
        "x",
    )
    assert p2 < p


def test_agrupar_similares():
    assert (
        similitud(
            "Beelink Mini S12 Pro N100 16GB 500GB", "Beelink Mini S12 Pro (16GB RAM, 500GB SSD) Intel N100"
        )
        >= 90
    )
    assert clave_canonica("x", None, None, "1234567890123", None) == "ean:1234567890123"
    grupos, dudosas = agrupar(
        [
            (1, "Beelink Mini S12 Pro N100 16GB 500GB", ""),
            (2, "Beelink Mini S12 Pro Intel N100 16GB RAM 500GB SSD Windows 11", ""),
            (3, "Minisforum UN100L 16GB 512GB", ""),
        ]
    )
    assert grupos[2] == 1 and grupos[3] == 3
