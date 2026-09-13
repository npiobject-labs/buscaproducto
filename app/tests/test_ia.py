"""La capa de IA con un cliente simulado: caché, costes, validación y adaptador universal."""

from types import SimpleNamespace

import pytest

from app.bd import BD
from app.costes import Costes
from app.dominio import Consulta, Interpretacion
from app.fuentes import Contexto, registro
from app.http import Http, html_a_markdown
from app.ia import Agentes, _ListaOfertas


class _ClienteFalso:
    def __init__(self, respuestas):
        self.respuestas, self.llamadas = respuestas, []
        self.messages = self

    async def parse(self, **kw):
        self.llamadas.append(kw)
        formato = kw["output_format"]
        salida = self.respuestas[formato.__name__]
        return SimpleNamespace(
            parsed_output=formato(**salida),
            usage=SimpleNamespace(input_tokens=1200, output_tokens=300, cache_read_input_tokens=0),
            stop_reason="end_turn",
        )


@pytest.fixture
async def agentes(ruta_bd, monkeypatch):
    from app import config as c

    monkeypatch.setattr(c.config, "anthropic_api_key", "clave-falsa")
    bd = BD()
    await bd.abrir()
    http = Http(bd)
    cliente = _ClienteFalso(
        {
            "Interpretacion": {
                "categoria": "minipc",
                "resumen": "Un mini PC con 8 GB o más, 500 GB, para 24/7, entre 130 y 330 €",
                "especificaciones": [
                    {"clave": "ram_gb", "operador": ">=", "valor": 8, "unidad": "GB", "peso": 4},
                    {"clave": "almacenamiento_gb", "operador": ">=", "valor": 500, "unidad": "GB", "peso": 3},
                    {"clave": "apto_24_7", "operador": "=", "valor": True, "blando": True, "peso": 3},
                    {"clave": "inventada", "operador": "=", "valor": "x"},
                ],
                "precio_min": 130,
                "precio_max": 330,
                "consulta_base": "mini pc 8gb 500gb",
                "confianza": 0.9,
            },
            "_LoteAtributos": {
                "elementos": [
                    {"id": 1, "ram_gb": 16, "almacenamiento_gb": 512, "cpu": "Intel N100"},
                    {"id": 2, "ram_gb": 8},
                ]
            },
            "_ListaOfertas": {
                "ofertas": [
                    {"url": "/p/123", "titulo": "Mini PC X 16GB 512GB", "precio": 199.0, "envio": 0},
                    {"url": "https://t.example/p/9", "titulo": "Mini PC Y 8GB", "precio": None},
                ]
            },
            "_Duplicados": {
                "parejas": [
                    {"a": 1, "b": 2, "mismo_producto": True, "confianza": 0.9},
                    {"a": 3, "b": 4, "mismo_producto": False, "confianza": 0.8},
                ]
            },
        }
    )
    ag = Agentes(bd, Costes(bd), http, cliente=cliente)
    yield ag, cliente, bd
    await http.cerrar()
    await bd.cerrar()


async def test_interpretar_valida_y_cachea(agentes):
    ag, cliente, bd = agentes
    inter = await ag.interpretar("minipc 8gb para 24/7 con 500gb entre 130 y 330")
    assert isinstance(inter, Interpretacion) and inter.precio_max == 330
    assert [s.clave for s in inter.especificaciones] == [
        "ram_gb",
        "almacenamiento_gb",
        "apto_24_7",
    ]  # la inventada se descarta
    assert (
        cliente.llamadas[0]["model"] == "claude-opus-5"
        and cliente.llamadas[0]["output_config"]["effort"] == "medium"
    )
    assert cliente.llamadas[0]["extra_body"] == {"fallbacks": "default"}
    await ag.interpretar("  MiniPC 8GB para 24/7 con 500gb entre 130 y 330 ")
    assert len(cliente.llamadas) == 1  # segunda desde caché (normalizada)
    costes = await Costes(bd).resumen()
    anthropic = next(c for c in costes if c["proveedor"] == "anthropic")
    assert anthropic["llamadas"] == 1 and anthropic["coste"] > 0
    assert (await bd.uno("SELECT COUNT(*) AS n FROM ejemplos"))["n"] == 1


async def test_extraer_atributos_en_lote(agentes):
    ag, cliente, _ = agentes
    r = await ag.extraer_atributos(
        [(1, "Mini PC X"), (2, "Mini PC Y"), (3, "Sin datos")], ["ram_gb", "almacenamiento_gb"]
    )
    assert (
        r[1] == {"ram_gb": 16, "almacenamiento_gb": 512, "cpu": "Intel N100"}
        and r[2] == {"ram_gb": 8}
        and r[3] == {}
    )
    assert cliente.llamadas[0]["model"] == "claude-haiku-4-5" and "thinking" not in cliente.llamadas[0]
    r2 = await ag.extraer_atributos([(9, "Mini PC X")], ["ram_gb"])
    assert r2[9]["ram_gb"] == 16 and len(cliente.llamadas) == 1  # caché por título


async def test_juzgar_duplicados(agentes):
    ag, _, _ = agentes
    assert await ag.juzgar_duplicados([(1, "a", 2, "b"), (3, "c", 4, "d")]) == [(1, 2)]


async def test_adaptador_universal(agentes):
    ag, cliente, bd = agentes
    h = {
        "id": 99,
        "slug": "mi-tienda",
        "nombre": "Mi tienda",
        "url_plantilla_busqueda": "https://t.example/buscar?q={q}",
        "necesita_js": 0,
        "nivel": "C",
    }
    ctx = Contexto(bd=bd, http=ag.http, herramienta=h, ia=ag)
    universal = registro()["universal"]
    assert universal.disponible(ctx) == (True, "")
    import respx

    with respx.mock(assert_all_called=True) as m:
        m.get("https://t.example/robots.txt").respond(404)
        m.get("https://t.example/buscar?q=mini+pc").respond(
            200,
            html="<html><body>"
            + "<p>relleno</p>" * 60
            + '<a href="/p/123">Mini PC X 16GB 512GB</a> 199 € <img src="https://t.example/i.jpg"></body></html>',
        )
        ofertas = await universal.buscar(Consulta(texto="mini pc"), ctx)
    assert [o.url for o in ofertas] == ["https://t.example/p/123"] and ofertas[0].precio == 199.0
    assert "[Mini PC X 16GB 512GB](https://t.example/p/123)" in cliente.llamadas[0]["messages"][0]["content"]
    assert cliente.llamadas[0]["output_format"] is _ListaOfertas


def test_html_a_markdown():
    md = html_a_markdown(
        '<html><head><style>x</style></head><body><script>1</script><div><a href="/p/1">Producto <b>uno</b></a><span>199,00 €</span></div></body></html>',
        "https://t.example/",
    )
    assert "[Producto uno](https://t.example/p/1)" in md and "199,00 €" in md and "script" not in md
