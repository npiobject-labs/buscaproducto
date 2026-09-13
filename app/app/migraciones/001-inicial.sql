CREATE TABLE IF NOT EXISTS herramientas (
  id INTEGER PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  nombre TEXT NOT NULL,
  categoria TEXT NOT NULL,
  url TEXT NOT NULL,
  url_plantilla_busqueda TEXT,
  tipo_acceso TEXT,
  coste TEXT,
  descripcion TEXT,
  origen TEXT NOT NULL DEFAULT 'predefinida',
  activa INTEGER NOT NULL DEFAULT 1,
  nivel TEXT NOT NULL DEFAULT 'D',
  adaptador TEXT,
  politica_scraping TEXT,
  necesita_js INTEGER NOT NULL DEFAULT 0,
  universal_ok INTEGER NOT NULL DEFAULT 0,
  config_json TEXT,
  creada TEXT NOT NULL,
  actualizada TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS busquedas (
  id TEXT PRIMARY KEY,
  texto TEXT,
  especificaciones_json TEXT NOT NULL DEFAULT '[]',
  precio_min REAL,
  precio_max REAL,
  estado_producto TEXT NOT NULL DEFAULT 'cualquiera',
  fuentes_json TEXT NOT NULL DEFAULT '[]',
  estado TEXT NOT NULL DEFAULT 'pendiente',
  interpretacion_json TEXT,
  facetas_json TEXT,
  error TEXT,
  creada TEXT NOT NULL,
  terminada TEXT
);

CREATE TABLE IF NOT EXISTS busqueda_fuentes (
  busqueda_id TEXT NOT NULL,
  herramienta_id INTEGER NOT NULL,
  slug TEXT NOT NULL,
  estado TEXT NOT NULL DEFAULT 'pendiente',
  n_ofertas INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  ms INTEGER,
  desde_cache INTEGER NOT NULL DEFAULT 0,
  nivel_usado TEXT,
  PRIMARY KEY (busqueda_id, herramienta_id)
);

CREATE TABLE IF NOT EXISTS productos (
  id INTEGER PRIMARY KEY,
  clave_canonica TEXT NOT NULL UNIQUE,
  nombre TEXT NOT NULL,
  marca TEXT,
  modelo TEXT,
  categoria TEXT,
  atributos_json TEXT NOT NULL DEFAULT '{}',
  imagen_url TEXT,
  actualizado TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ofertas (
  id INTEGER PRIMARY KEY,
  producto_id INTEGER REFERENCES productos(id),
  herramienta_id INTEGER NOT NULL,
  url TEXT NOT NULL,
  titulo TEXT NOT NULL,
  precio REAL,
  envio REAL,
  moneda TEXT NOT NULL DEFAULT 'EUR',
  estado_producto TEXT,
  disponibilidad TEXT,
  vendedor TEXT,
  valoracion REAL,
  n_valoraciones INTEGER,
  imagen_url TEXT,
  atributos_json TEXT NOT NULL DEFAULT '{}',
  hash TEXT NOT NULL UNIQUE,
  primera_vez TEXT NOT NULL,
  ultima_vez TEXT NOT NULL,
  vigilada INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_ofertas_producto ON ofertas(producto_id);

CREATE TABLE IF NOT EXISTS busqueda_ofertas (
  busqueda_id TEXT NOT NULL,
  oferta_id INTEGER NOT NULL,
  puntuacion REAL NOT NULL DEFAULT 0,
  explicacion_json TEXT NOT NULL DEFAULT '[]',
  posicion INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (busqueda_id, oferta_id)
);

CREATE TABLE IF NOT EXISTS precios (
  id INTEGER PRIMARY KEY,
  oferta_id INTEGER NOT NULL REFERENCES ofertas(id),
  fecha TEXT NOT NULL,
  precio REAL,
  envio REAL
);
CREATE INDEX IF NOT EXISTS ix_precios_oferta ON precios(oferta_id, fecha);

CREATE TABLE IF NOT EXISTS alertas (
  id INTEGER PRIMARY KEY,
  tipo TEXT NOT NULL,
  busqueda_id TEXT,
  oferta_id INTEGER,
  umbral REAL,
  canal TEXT NOT NULL DEFAULT 'telegram',
  activa INTEGER NOT NULL DEFAULT 1,
  ultima_comprobacion TEXT,
  ultimo_disparo TEXT,
  creada TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cache_http (
  clave TEXT PRIMARY KEY,
  url TEXT NOT NULL,
  estado INTEGER NOT NULL,
  cuerpo BLOB,
  cabeceras_json TEXT,
  obtenido TEXT NOT NULL,
  expira TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS informes (
  id INTEGER PRIMARY KEY,
  tipo TEXT NOT NULL,
  clave TEXT NOT NULL,
  contenido_json TEXT NOT NULL,
  citas_json TEXT,
  modelo TEXT,
  tokens_in INTEGER NOT NULL DEFAULT 0,
  tokens_out INTEGER NOT NULL DEFAULT 0,
  creado TEXT NOT NULL,
  expira TEXT,
  UNIQUE (tipo, clave)
);

CREATE TABLE IF NOT EXISTS costes_api (
  id INTEGER PRIMARY KEY,
  fecha TEXT NOT NULL,
  proveedor TEXT NOT NULL,
  unidades REAL NOT NULL DEFAULT 0,
  coste_estimado REAL NOT NULL DEFAULT 0,
  detalle TEXT
);
CREATE INDEX IF NOT EXISTS ix_costes_fecha ON costes_api(proveedor, fecha);

CREATE TABLE IF NOT EXISTS eventos (
  id INTEGER PRIMARY KEY,
  fecha TEXT NOT NULL,
  nivel TEXT NOT NULL DEFAULT 'info',
  fuente TEXT,
  mensaje TEXT NOT NULL,
  datos_json TEXT
);

CREATE TABLE IF NOT EXISTS ejemplos (
  id INTEGER PRIMARY KEY,
  texto TEXT NOT NULL,
  interpretacion_json TEXT,
  correccion_json TEXT,
  creado TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS fuente_stats (
  id INTEGER PRIMARY KEY,
  slug TEXT NOT NULL,
  fecha TEXT NOT NULL,
  n_ofertas INTEGER NOT NULL,
  estado TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_fuente_stats ON fuente_stats(slug, fecha);

-- tipo de fila en ofertas: 'oferta' (con precio) o 'enlace' (nivel D)
ALTER TABLE ofertas ADD COLUMN tipo TEXT NOT NULL DEFAULT 'oferta';
