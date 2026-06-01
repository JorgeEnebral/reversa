"""
Panel lateral derecho con la información del nodo o arista seleccionado.

Se activa al clicar en el grafo (el evento llega desde ``sigma_canvas.py``
vía sondeo de ``window.getLastClick()``) y se oculta con el botón ✕.
Permanece oculto hasta el primer click para no ocupar espacio innecesario
cuando el usuario solo está explorando visualmente el grafo.
"""

from __future__ import annotations

from typing import Any

from nicegui import ui


class InfoPanel:
    """Panel de detalle de nodo o arista seleccionado en el grafo.

    Args:
        width: Ancho del panel en píxeles.
    """

    def __init__(self, width: int = 300) -> None:
        self._width = width
        with ui.card().style(
            f"width:{width}px;height:100%;overflow-y:auto;"
            "background:var(--surface);color:var(--text);"
            "border-left:1px solid var(--border);border-radius:0;"
            "box-shadow:none;padding:16px;"
        ) as self._card:
            with ui.row().classes("w-full justify-between items-center"):
                self._title = ui.label("Selecciona un elemento").style(
                    "font-weight:700;font-size:1.05em;color:var(--text);"
                )
                ui.button("✕", on_click=self.clear).props("flat dense").style(
                    "color:var(--text-muted);"
                )
            self._content = ui.column().classes("w-full gap-1")
        # Oculto al inicio: set_visibility(False) no elimina el espacio en el DOM,
        # pero el panel tiene width fijo, así que el layout no cambia al abrirlo.
        self._card.set_visibility(False)

    def show_node(self, node: dict[str, Any]) -> None:
        """Muestra los atributos de un nodo en el panel.

        Args:
            node: Dict con ``"id"`` y ``"attrs"`` (properties del nodo Neo4j).
        """
        self._card.set_visibility(True)
        self._title.set_text(f"Nodo: {node.get('id', '')[:30]}")
        self._content.clear()
        with self._content:
            _render_attrs(node.get("attrs", {}))

    def show_edge(self, edge: dict[str, Any]) -> None:
        """Muestra los atributos de una arista en el panel.

        Args:
            edge: Dict con ``"id"``, ``"src"``, ``"dst"`` y ``"attrs"``.
        """
        self._card.set_visibility(True)
        label = edge.get("attrs", {}).get("label", edge.get("id", ""))
        self._title.set_text(f"Arista: {label}")
        self._content.clear()
        with self._content:
            ui.label(f"Origen: {edge.get('src', '')}").style("font-size:0.85em;")
            ui.label(f"Destino: {edge.get('dst', '')}").style("font-size:0.85em;")
            _render_attrs(edge.get("attrs", {}))

    def clear(self) -> None:
        """Oculta el panel y limpia su contenido."""
        self._card.set_visibility(False)
        self._content.clear()


def _render_attrs(attrs: dict[str, Any]) -> None:
    """Renderiza pares clave-valor como etiquetas dentro del panel.

    Omite atributos ``None`` y los campos ``*_codigo`` (identificadores
    internos de relación del BOE que no aportan valor al usuario final).

    Args:
        attrs: Propiedades del nodo o arista extraídas de Neo4j.
    """
    for key, value in attrs.items():
        if value is None:
            continue
        # Los campos *_codigo son enteros de referencia interna del BOE (p.ej.
        # codigo_relacion=270); se omiten porque son opacos para el usuario.
        if key.endswith("_codigo"):
            continue
        ui.label(f"{key}: {value}").style("font-size:0.82em;word-break:break-all;")
