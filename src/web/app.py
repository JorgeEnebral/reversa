"""
Registro de rutas NiceGUI de Reversa.

Crea la instancia de la app y registra todas las páginas.
NiceGUI expone su propio servidor FastAPI vía `nicegui.app`;
no hace falta crear una instancia FastAPI separada.
"""

from __future__ import annotations

from nicegui import app, ui

from src.web.pages.chat import register_chat_page
from src.web.pages.graph import register_graph_page


def create_app() -> None:
    """Registra todas las rutas de NiceGUI.

    Debe llamarse antes de ui.run() para que las páginas estén disponibles.
    """
    ui.dark_mode().enable()

    # Estilos globales
    ui.add_head_html(
        "<style>"
        "body { margin: 0; font-family: 'Segoe UI', sans-serif; }"
        "* { box-sizing: border-box; }"
        "</style>"
    )

    register_chat_page()
    register_graph_page()

    # Endpoint de la API interna (ping de salud)
    @app.get("/api/health")
    async def health() -> dict[str, str]:
        """Healthcheck para monitorización."""
        return {"status": "ok"}
