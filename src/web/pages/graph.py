"""
Página /graph — visualización del grafo de normas con Sigma.js.

Layout: sidebar filtros (izq) | canvas Sigma (centro) | panel info (dcha).
Carga desde Neo4j y pasa los datos a Sigma vía sigma_bridge.js.
"""

from __future__ import annotations

from typing import Any

import structlog
from neo4j import GraphDatabase
from nicegui import app, ui

from src.config import settings
from src.web.components.filter_panel import FilterPanel
from src.web.components.info_panel import InfoPanel
from src.web.components.sigma_canvas import SigmaCanvas

log = structlog.get_logger()

# CDN de graphology + Sigma (cargados una sola vez en el head de la página)
_SIGMA_CDN = [
    "https://unpkg.com/graphology@0.25.4/dist/graphology.umd.js",
    "https://unpkg.com/sigma@2.4.0/build/sigma.js",
]

_MAX_NODES = 2000  # tope de nodos enviados al frontend (WebGL aguanta más)
_MAX_EDGES = 8000


def _query_graph(filters: dict[str, Any]) -> dict[str, Any]:
    """Consulta Neo4j y devuelve {nodes, edges} en formato sigma_bridge.

    Args:
        filters: dict de filtros activos del panel (vigente, rango, etc.).

    Returns:
        Dict con listas 'nodes' y 'edges'.
    """
    driver = GraphDatabase.driver(
        settings.neo4j.uri,
        auth=(settings.neo4j.user, settings.neo4j.password),
    )

    where_clauses: list[str] = []
    params: dict[str, Any] = {}

    if "vigente" in filters:
        where_clauses.append("n.vigente = $vigente")
        params["vigente"] = filters["vigente"]
    if "rango" in filters:
        where_clauses.append("toLower(n.rango) CONTAINS toLower($rango)")
        params["rango"] = filters["rango"]
    if "departamento" in filters:
        where_clauses.append(
            "toLower(n.departamento) CONTAINS toLower($departamento)"
        )
        params["departamento"] = filters["departamento"]
    if "anyo_desde" in filters:
        where_clauses.append("n.fecha_publicacion >= $anyo_desde")
        params["anyo_desde"] = f"{filters['anyo_desde']}-01-01"
    if "anyo_hasta" in filters:
        where_clauses.append("n.fecha_publicacion <= $anyo_hasta")
        params["anyo_hasta"] = f"{filters['anyo_hasta']}-12-31"

    where_str = (
        ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    )

    node_q = f"MATCH (n:Norma) {where_str} RETURN n LIMIT {_MAX_NODES}"
    edge_q = (
        f"MATCH (a:Norma)-[r]->(b:Norma) {where_str.replace('n.', 'a.')} "
        f"RETURN a.id AS src, type(r) AS type, b.id AS dst, r.texto AS texto "
        f"LIMIT {_MAX_EDGES}"
    )

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    try:
        with driver.session(database=settings.neo4j.database) as session:
            for record in session.run(node_q, **params):
                nd = dict(record["n"])
                nodes.append(
                    {
                        "id": nd.get("id", ""),
                        "label": (nd.get("titulo") or nd.get("id") or "")[:40],
                        "attrs": nd,
                    }
                )
            node_ids = {n["id"] for n in nodes}
            for record in session.run(edge_q, **params):
                src = record["src"]
                dst = record["dst"]
                if src in node_ids and dst in node_ids:
                    edges.append(
                        {
                            "src": src,
                            "dst": dst,
                            "type": record["type"],
                            "attrs": {"texto": record.get("texto") or ""},
                        }
                    )
    except Exception as exc:  # noqa: BLE001
        log.warning("graph_query_failed", error=str(exc))
    finally:
        driver.close()

    return {"nodes": nodes, "edges": edges}


def register_graph_page() -> None:
    """Registra la ruta /graph en NiceGUI."""

    app.add_static_files("/static", "src/web/static")

    @ui.page("/graph")
    async def graph_page() -> None:
        """Página de visualización del grafo."""
        for cdn_url in _SIGMA_CDN:
            ui.add_head_html(f'<script src="{cdn_url}"></script>')
        ui.add_head_html(
            '<script src="/static/sigma_bridge.js" defer></script>'
        )
        ui.add_head_html(
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
        )

        # Header
        from src.web.pages.chat import (
            build_chat_header,
        )  # local import para evitar ciclo

        build_chat_header()

        info_panel = InfoPanel()
        sigma_canvas: SigmaCanvas | None = None

        async def on_node_click(node: dict[str, Any]) -> None:
            info_panel.show_node(node)

        async def on_edge_click(edge: dict[str, Any]) -> None:
            info_panel.show_edge(edge)

        async def apply_filters(filters: dict[str, Any]) -> None:
            nonlocal sigma_canvas
            status_label.set_text("Cargando grafo…")
            graph_data = _query_graph(filters)
            n_nodes = len(graph_data["nodes"])
            n_edges = len(graph_data["edges"])
            status_label.set_text(f"{n_nodes} nodos · {n_edges} aristas")
            if sigma_canvas is not None:
                await sigma_canvas.load_graph(graph_data)

        with ui.row().style(
            "width:100%;height:calc(100vh - 60px);gap:0;overflow:hidden;"
        ):
            # Panel izquierdo — filtros
            FilterPanel(on_apply=apply_filters, width=220)

            # Canvas central
            with ui.column().style("flex:1;height:100%;position:relative;"):
                status_label = ui.label("Cargando…").style(
                    "position:absolute;top:8px;left:8px;z-index:10;"
                    "color:#aaa;font-size:0.82em;"
                )
                sigma_canvas = SigmaCanvas(
                    on_node_click=on_node_click,
                    on_edge_click=on_edge_click,
                    height=0,
                )

            # Panel derecho — info
            info_panel = InfoPanel(width=280)

        # Carga inicial del grafo completo (sin filtros)
        await apply_filters({})
