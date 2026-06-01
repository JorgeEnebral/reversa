"""
Registro de rutas NiceGUI de Reversa.

NiceGUI expone su propio servidor FastAPI vía ``nicegui.app``; no hace falta
crear una instancia FastAPI separada. Todas las páginas se registran aquí
antes de que ``ui.run()`` arranque el servidor en ``src/main.py``.

Sistema de diseño
-----------------
Los estilos globales (``_GLOBAL_STYLES``) se inyectan en el ``<head>`` de
cada página. Usan variables CSS (``--bg``, ``--brand``, etc.) para que los
componentes no necesiten conocer los valores concretos de los colores: basta
con que usen las variables. Esto centraliza el tema en un único lugar.

Las fuentes se cargan desde Google Fonts (``preconnect`` + ``display=swap``
para evitar FOIT). Si el entorno no tiene acceso a internet, el navegador
usará la pila de fuentes ``system-ui`` definida en el CSS base.
"""

from __future__ import annotations

from nicegui import app

from src.web.pages.chat import register_chat_page
from src.web.pages.graph import register_graph_page


# Variables CSS del tema Reversa: claro, navy (#13283D) sobre blanco.
# Se definen en :root para que sean accesibles globalmente via var(--nombre).
_GLOBAL_STYLES = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #ffffff;
    --bg-soft: #f6f8fb;
    --surface: #ffffff;
    --border: #e4e7ec;
    --text: #13283d;
    --text-muted: #667085;
    --brand: #13283d;
    --brand-hover: #20405f;
    --bot-bubble: #f2f4f7;
  }
  html, body {
    margin: 0;
    background: var(--bg);
    color: var(--text);
    font-family: 'Inter', 'Segoe UI', system-ui, -apple-system, sans-serif;
  }
  * { box-sizing: border-box; }
  a { text-decoration: none; }
  /* Elimina el padding por defecto de NiceGUI para que chat y grafo
     puedan ocupar la ventana completa sin huecos. */
  .nicegui-content { padding: 0; gap: 0; }
  /* Scrollbars discretos: finos y sin track visible. */
  ::-webkit-scrollbar { width: 8px; height: 8px; }
  ::-webkit-scrollbar-thumb { background: #d0d5dd; border-radius: 8px; }
  ::-webkit-scrollbar-thumb:hover { background: #b8bfc9; }
  ::-webkit-scrollbar-track { background: transparent; }
</style>
"""


def create_app() -> None:
    """Registra todas las rutas NiceGUI.

    Debe llamarse antes de ``ui.run()`` para que las páginas estén disponibles
    desde el primer request. NiceGUI no admite registro de rutas en caliente
    (después de que el servidor haya arrancado).
    """
    # Sirve el logo y demás recursos estáticos en /resources.
    app.add_static_files("/resources", "resources")

    register_chat_page(_GLOBAL_STYLES)
    register_graph_page(_GLOBAL_STYLES)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        """Healthcheck para monitorización y readiness probes."""
        return {"status": "ok"}
