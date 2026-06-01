"""
Página /graph — visualización interactiva del grafo de normas con Sigma.js.

Arquitectura de la página
-------------------------
La página sigue el principio de separación estricta de capas:

  FilterPanel (izq.)  →  apply_filters()  →  graph_repo.fetch_graph()
                                                        ↓
  InfoPanel (dcha.)  ←  on_node/edge_click  ←  SigmaCanvas.load_graph()

``graph.py`` solo orquesta la UI; no contiene Cypher ni lógica de datos.

Carga de librerías JS
---------------------
Las librerías se sirven desde ``/static/vendor/`` (no CDN) en el orden
correcto de dependencias:
  1. graphology.umd.min.js    – estructura de datos del grafo
  2. graphology-library.min.js – algoritmos de layout (ForceAtlas2)
  3. sigma.min.js              – renderer WebGL (requiere graphology en global)

``sigma_bridge.js`` espera que los tres estén disponibles como globales antes
de ejecutarse; el atributo ``defer`` garantiza que corre después del parsing
del HTML pero antes del primer ``initSigma()``.
"""

from __future__ import annotations

from typing import Any

import structlog
from nicegui import app, context, ui

from src.web.components.filter_panel import FilterPanel
from src.web.components.info_panel import InfoPanel
from src.web.components.sigma_canvas import SigmaCanvas
from src.web.data.graph_repo import Scope, fetch_graph

log = structlog.get_logger()

# Librerías JS vendorizadas. El orden importa: graphology primero porque
# sigma.min.js y graphology-library.min.js lo referencian como global.
_VENDOR_SCRIPTS = [
    "/static/vendor/graphology.umd.min.js",
    "/static/vendor/graphology-library.min.js",
    "/static/vendor/sigma.min.js",
]


def register_graph_page(global_styles: str = "") -> None:
    """Registra la ruta ``/graph`` en NiceGUI.

    Args:
        global_styles: HTML de estilos globales inyectado en el ``<head>``
            (fuentes, variables CSS, reset); proviene de ``app.py``.
    """
    # add_static_files se llama una sola vez; NiceGUI deduplica rutas repetidas.
    app.add_static_files("/static", "src/web/static")

    @ui.page("/graph")
    async def graph_page() -> None:
        """Página de visualización del grafo."""
        for src in _VENDOR_SCRIPTS:
            # Scripts síncronos (sin defer) para que estén disponibles cuando
            # sigma_bridge.js (defer) los necesite.
            ui.add_head_html(f'<script src="{src}"></script>')
        # v=4 fuerza recarga del caché al desplegar nuevas versiones del bridge.
        ui.add_head_html('<script src="/static/sigma_bridge.js?v=4" defer></script>')
        ui.add_head_html(
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
        )
        if global_styles:
            ui.add_head_html(global_styles)

        from src.web.pages.chat import build_chat_header  # evita ciclo de importación

        build_chat_header()

        info_panel: InfoPanel

        async def on_node_click(node: dict[str, Any]) -> None:
            info_panel.show_node(node)

        async def on_edge_click(edge: dict[str, Any]) -> None:
            info_panel.show_edge(edge)

        async def apply_filters(filters: dict[str, Any]) -> None:
            """Recarga el grafo con los filtros y scope del panel lateral."""
            # scope se extrae aquí y no llega a build_where; fetch_graph lo recibe
            # como argumento tipado (Scope) en lugar de como clave en el dict.
            scope: Scope = filters.pop("scope", "norma")
            status_label.set_text("Cargando grafo…")
            graph_data = fetch_graph(scope, filters)
            n_nodes = len(graph_data["nodes"])
            n_edges = len(graph_data["edges"])
            status_label.set_text(f"{n_nodes} nodos · {n_edges} aristas")
            if sigma_canvas is not None:
                await sigma_canvas.load_graph(graph_data)

        with ui.row().style(
            "width:100%;height:calc(100vh - 60px);gap:0;overflow:hidden;"
        ):
            FilterPanel(on_apply=apply_filters, width=240)

            # position:relative aquí es el ancla para el #sigma-canvas
            # que usa position:absolute;inset:0 en SigmaCanvas.
            with ui.column().style(
                "flex:1;height:100%;position:relative;background:var(--bg-soft);"
            ):
                status_label = ui.label("Cargando…").style(
                    "position:absolute;top:10px;left:10px;z-index:10;color:var(--text-muted);"
                    "font-size:0.82em;background:rgba(255,255,255,0.9);padding:4px 10px;"
                    "border-radius:8px;border:1px solid var(--border);"
                )
                sigma_canvas = SigmaCanvas(
                    on_node_click=on_node_click,
                    on_edge_click=on_edge_click,
                )

            info_panel = InfoPanel(width=300)

        # context.client.connected() garantiza que el websocket esté abierto
        # antes de llamar a run_javascript (initSigma). Sin esta espera,
        # el primer apply_filters lanzaría el JS antes de que el canal esté listo.
        await context.client.connected()
        await apply_filters({})
