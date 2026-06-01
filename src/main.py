"""
Punto de entrada principal de Reversa.

Arranca la interfaz web NiceGUI (que incluye su propio servidor uvicorn).
Para el pipeline de descarga + preprocesado usar api.py / preprocess.py
directamente o crear un comando CLI separado.

Ejecutar:
    uv run python -m src.main
"""

from nicegui import ui

from src.config import settings
from src.web import create_app


def main() -> None:
    """Registra las páginas y arranca NiceGUI."""
    create_app()
    ui.run(
        host=settings.web.host,
        port=settings.web.port,
        title=settings.web.title,
        reload=False,
        dark=False,
    )


if __name__ == "__main__":
    main()
