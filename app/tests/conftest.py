import os
from pathlib import Path

os.environ.setdefault("BP_CLAVE", "clave-de-prueba")
os.environ.setdefault("BP_INTERVALO_DOMINIO", "0")
os.environ.setdefault("BP_TIMEOUT_FUENTE", "5")

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app import config as _config  # noqa: E402


@pytest.fixture
def ruta_bd(tmp_path: Path, monkeypatch):
    ruta = tmp_path / "prueba.sqlite"
    monkeypatch.setattr(_config.config, "ruta_bd", ruta)
    monkeypatch.setattr(_config.config, "intervalo_dominio_s", 0.0)
    return ruta


@pytest.fixture
async def cliente(ruta_bd):
    from app.main import crear_app

    app = crear_app()
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test", headers={"X-Clave": "clave-de-prueba"}
        ) as c:
            c.app = app  # type: ignore[attr-defined]
            yield c
