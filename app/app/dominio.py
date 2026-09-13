"""Modelos comunes (pydantic) compartidos por API, pipeline de búsqueda, adaptadores e IA."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

Operador = Literal[">=", "<=", "=", "~", "!="]
EstadoProducto = Literal["cualquiera", "nuevo", "reacondicionado", "segunda_mano"]
Nivel = Literal["A", "B", "C", "D"]

# Claves de atributos conocidas: el Extractor y el Intérprete se limitan a estas (y a `otros`).
ATRIBUTOS = {
    "ram_gb": ("RAM", "GB", "numero"),
    "almacenamiento_gb": ("Almacenamiento", "GB", "numero"),
    "cpu": ("Procesador", "", "texto"),
    "gpu": ("Gráfica", "", "texto"),
    "tdp_w": ("Consumo (TDP)", "W", "numero"),
    "pantalla_pulgadas": ("Pantalla", '"', "numero"),
    "resolucion": ("Resolución", "", "texto"),
    "peso_kg": ("Peso", "kg", "numero"),
    "bateria_wh": ("Batería", "Wh", "numero"),
    "wifi": ("WiFi", "", "texto"),
    "ethernet_gbps": ("Ethernet", "Gbps", "numero"),
    "puertos_usb": ("Puertos USB", "", "numero"),
    "sistema_operativo": ("Sistema operativo", "", "texto"),
    "fanless": ("Sin ventilador", "", "booleano"),
    "apto_24_7": ("Apto 24/7", "", "booleano"),
    "silencioso": ("Silencioso", "", "booleano"),
    "pantalla_mate": ("Pantalla mate", "", "booleano"),
    "openwrt": ("Compatible OpenWrt", "", "booleano"),
    "formato": ("Formato", "", "texto"),
    "color": ("Color", "", "texto"),
    "marca": ("Marca", "", "texto"),
    "modelo": ("Modelo", "", "texto"),
    "anio": ("Año", "", "numero"),
}

# Atributos que no salen en la ficha y necesitan al Investigador o heurística.
ATRIBUTOS_BLANDOS = {"apto_24_7", "silencioso", "fiable"}


class Especificacion(BaseModel):
    clave: str
    operador: Operador = ">="
    valor: str | float | bool
    unidad: str = ""
    peso: float = Field(default=1.0, ge=0, le=5)
    blando: bool = False

    @field_validator("clave")
    @classmethod
    def _normalizar_clave(cls, v: str) -> str:
        return v.strip().lower().replace(" ", "_")


class Consulta(BaseModel):
    """Lo que recibe un adaptador: la consulta ya adaptada a esa fuente."""

    texto: str
    especificaciones: list[Especificacion] = []
    precio_min: float | None = None
    precio_max: float | None = None
    estado: EstadoProducto = "cualquiera"


class OfertaCruda(BaseModel):
    """Lo que devuelve un adaptador, sin normalizar."""

    url: str
    titulo: str
    precio: float | None = None
    envio: float | None = None
    moneda: str = "EUR"
    estado_producto: str | None = None
    disponibilidad: str | None = None
    vendedor: str | None = None
    valoracion: float | None = None
    n_valoraciones: int | None = None
    imagen_url: str | None = None
    texto_extra: str | None = None
    ean: str | None = None
    asin: str | None = None
    atributos: dict[str, Any] = {}
    tipo: Literal["oferta", "enlace"] = "oferta"


class PeticionBusqueda(BaseModel):
    texto: str | None = None
    especificaciones: list[Especificacion] = []
    precio_min: float | None = Field(default=None, ge=0)
    precio_max: float | None = Field(default=None, ge=0)
    estado: EstadoProducto = "cualquiera"
    fuentes: list[str] | None = None  # slugs; None = todas las activas
    interpretar: bool = True
    mostrar_fuera_rango: bool = False
    usar_cache: bool = True

    @field_validator("precio_max")
    @classmethod
    def _rango(cls, v: float | None, info) -> float | None:
        minimo = info.data.get("precio_min")
        if v is not None and minimo is not None and v < minimo:
            raise ValueError("precio_max debe ser mayor o igual que precio_min")
        return v


class HerramientaEntrada(BaseModel):
    nombre: str = Field(min_length=1, max_length=120)
    categoria: str = Field(default="otra", max_length=60)
    url: str = Field(pattern=r"^https?://")
    url_plantilla_busqueda: str | None = None
    tipo_acceso: str | None = None
    coste: str | None = None
    descripcion: str | None = None
    activa: bool = True
    necesita_js: bool = False

    @field_validator("url_plantilla_busqueda")
    @classmethod
    def _plantilla(cls, v: str | None) -> str | None:
        if v is None or not v.strip():
            return None
        v = v.strip()
        if "{q}" not in v or not v.startswith("http"):
            raise ValueError("la plantilla debe empezar por http y contener {q}")
        return v


class Interpretacion(BaseModel):
    """Salida del Intérprete: lo que se ha entendido de un texto libre."""

    categoria: str = "generica"
    resumen: str = ""
    especificaciones: list[Especificacion] = []
    precio_min: float | None = None
    precio_max: float | None = None
    estado: EstadoProducto = "cualquiera"
    consulta_base: str = ""
    consultas_por_fuente: dict[str, str] = {}
    confianza: float = Field(default=0.5, ge=0, le=1)
