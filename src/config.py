"""
Configuración centralizada de Reversa.

Cada clase representa un grupo de settings; se instancia una vez al importar
y se usa como singleton inmutable desde cualquier módulo.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class APIConfig(BaseSettings):
    """Endpoints y rutas de persistencia de la API del BOE."""

    base_url: str = "https://www.boe.es/datosabiertos/api"
    timeout: int = 30
    data_dir: Path = Path("data_api")

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def errors_dir(self) -> Path:
        return self.data_dir / "errors"

    @property
    def ids_file(self) -> Path:
        return self.raw_dir / "ids.txt"

    model_config = {"frozen": True}


API_CONFIG = APIConfig()
