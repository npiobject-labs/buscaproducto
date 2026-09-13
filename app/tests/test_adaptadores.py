import json
from pathlib import Path

from app.dominio import Consulta
from app.fuentes import chollometro, ebay, google_shopping, registro

FIXTURES = Path(__file__).resolve().parents[1] / "app" / "fuentes" / "fixtures"


def test_registro_descubre_adaptadores():
    reg = registro()
    assert {"enlace", "universal", "ebay", "google-shopping", "chollometro"} <= set(reg)


def test_ebay_parsea_fixture():
    datos = json.loads((FIXTURES / "ebay" / "busqueda-minipc.json").read_text(encoding="utf-8"))
    ofertas = ebay.parsear(datos)
    assert len(ofertas) == 3
    o = ofertas[0]
    assert o.precio == 189.0 and o.envio == 0.0 and o.vendedor == "tienda_es" and o.imagen_url
    assert ofertas[1].envio == 4.99 and ofertas[2].estado_producto.startswith("Reacond")
    assert (
        ebay.Adaptador().filtro(Consulta(texto="x", precio_min=130, precio_max=330, estado="nuevo"))
        == "deliveryCountry:ES,priceCurrency:EUR,price:[130.0..330.0],conditions:{NEW}"
    )


def test_serper_parsea_fixture():
    datos = json.loads((FIXTURES / "google-shopping" / "busqueda-minipc.json").read_text(encoding="utf-8"))
    ofertas = google_shopping.parsear(datos)
    assert len(ofertas) == 4
    assert ofertas[0].precio == 199.99 and ofertas[0].envio == 0.0 and ofertas[0].vendedor == "PcComponentes"
    assert ofertas[2].precio == 249.0 and ofertas[2].envio == 4.99


def test_chollometro_parsea_fixture_real():
    html = (FIXTURES / "chollometro" / "busqueda-minipc.html").read_text(encoding="utf-8")
    ofertas = chollometro.parsear(html)
    # la fixture trae 30 chollos, 25 caducados: solo se devuelven los vigentes
    assert len(ofertas) == 5 and all(o.precio for o in ofertas)
    o = ofertas[0]
    assert (
        o.url.startswith("https://www.chollometro.com/ofertas/")
        and o.vendedor
        and o.precio == 174.17
        and o.envio == 0.0
    )
    assert all(o.disponibilidad != "expirado" for o in ofertas)
