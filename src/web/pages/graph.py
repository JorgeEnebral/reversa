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
from src.web.data.graph_repo import fetch_graph, fetch_neighbors

log = structlog.get_logger()

_VENDOR_SCRIPTS = [
    "/static/vendor/graphology.umd.min.js",
    "/static/vendor/graphology-library.min.js",
    "/static/vendor/sigma.min.js",
]


def register_graph_page(global_styles: str = "") -> None:
    """Registra la ruta ``/graph`` en NiceGUI.

    Args:
        global_styles: HTML de estilos globales inyectado en el ``<head>``.
    """
    app.add_static_files("/static", "src/web/static")

    @ui.page("/graph")
    async def graph_page() -> None:
        """Página de visualización del grafo."""
        for src in _VENDOR_SCRIPTS:
            ui.add_head_html(f'<script src="{src}"></script>')
        # v=9 fuerza recarga del caché al desplegar nuevas versiones del bridge.
        ui.add_head_html('<script src="/static/sigma_bridge.js?v=9" defer></script>')
        ui.add_head_html('<meta name="viewport" content="width=device-width,initial-scale=1">')
        if global_styles:
            ui.add_head_html(global_styles)

        from src.web.pages.chat import build_chat_header  # evita ciclo de importación

        build_chat_header()

        # Variables capturadas por los closures; se asignan en el bloque ui.row.
        sigma_canvas: SigmaCanvas
        status_label: ui.label
        info_panel: InfoPanel

        async def on_node_click(node: dict[str, Any]) -> None:
            info_panel.show_node(node)

        async def on_edge_click(edge: dict[str, Any]) -> None:
            info_panel.show_edge(edge)

        async def apply_filters(filters: dict[str, Any]) -> None:
            """Recarga el grafo con los filtros del panel lateral."""
            status_label.set_text("Cargando grafo…")
            graph_data = fetch_graph(filters)
            n_nodes = len(graph_data["nodes"])
            n_edges = len(graph_data["edges"])
            status_label.set_text(f"{n_nodes} nodos · {n_edges} aristas")
            if sigma_canvas is not None:
                await sigma_canvas.load_graph(graph_data)

        async def show_neighbors(node: dict[str, Any], direction: str = "both") -> None:
            """Carga el nodo dado y sus vecinos en el canvas según la dirección."""
            node_id = node.get("id", "").strip()
            if not node_id:
                return
            status_label.set_text("Cargando vecinos…")
            graph_data = fetch_neighbors(node_id, direction)
            n_nodes = len(graph_data["nodes"])
            n_edges = len(graph_data["edges"])
            status_label.set_text(f"{n_nodes} nodos · {n_edges} aristas")
            if sigma_canvas is not None:
                await sigma_canvas.load_graph(graph_data)

        with ui.row().style("width:100%;height:calc(100vh - 60px);gap:0;overflow:hidden;"):
            FilterPanel(on_apply=apply_filters, width=340)

            # position:relative es el ancla para el #sigma-canvas (position:absolute;inset:0).
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

            info_panel = InfoPanel(width=400, on_show_neighbors=show_neighbors)

        context.client.on_disconnect(sigma_canvas.stop)
        await context.client.connected()
        await apply_filters({})
