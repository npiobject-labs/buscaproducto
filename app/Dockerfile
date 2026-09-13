# --- Etapa de dependencias ---
FROM python:3.12-slim-bookworm AS builder

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
# El entorno se crea directamente en /app/.venv: los lanzadores del venv llevan el
# interprete en el shebang con ruta absoluta, asi que construirlo en otra ruta y
# copiarlo despues deja "uvicorn: not found" en tiempo de ejecucion.
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /src

# Primero solo los manifiestos, para cachear la instalacion de dependencias.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app

# --- Etapa de ejecucion ---
FROM python:3.12-slim-bookworm AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --system --create-home --uid 10001 buscaproducto \
    && mkdir -p /datos && chown buscaproducto:buscaproducto /datos
WORKDIR /app
COPY --from=builder --chown=buscaproducto:buscaproducto /app/.venv /app/.venv
COPY --from=builder --chown=buscaproducto:buscaproducto /src/app /app/app
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Se arranca como root solo para ajustar el propietario del volumen montado; entrypoint.sh
# baja a uid 10001 antes de ejecutar el CMD.
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PUERTO=8080 BP_BD=/datos/buscaproducto.sqlite

# Red de seguridad: si el entorno o la app no importan, falla la construccion, no el arranque.
RUN /app/.venv/bin/python -c "import uvicorn, app.main; print('imagen ok:', app.main.app.title)"

EXPOSE 8080

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
# Ruta absoluta del interprete: no depende del PATH ni del shebang de los lanzadores.
CMD ["sh", "-c", "exec /app/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port ${PUERTO:-8080} --no-access-log"]
