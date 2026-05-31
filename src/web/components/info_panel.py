"""
Panel lateral derecho con la información del nodo o arista seleccionado.

Se muestra al clicar en el grafo y se cierra con el botón ✕.
"""

from __future__ import annotations

from typing import Any

from nicegui import ui


class InfoPanel:
    """Panel de información de nodo/arista seleccionado.

    Args:
        width: ancho del panel en píxeles.
    """

    def __init__(self, width: int = 300) -> None:
        self._width = width
        with ui.card().style(
            f"width:{width}px;height:100%;overflow-y:auto;"
            "background:#1e1e3f;color:#e0e0e0;"
        ) as self._card:
            with ui.row().classes("w-full justify-between items-center"):
                self._title = ui.label("Selecciona un elemento").style(
                    "font-weight:bold;font-size:1.1em;"
                )
                ui.button("✕", on_click=self.clear).props("flat dense").style(
                    "color:#e0e0e0;"
                )
            self._content = ui.column().classes("w-full gap-1")
        self._card.set_visibility(False)

    def show_node(self, node: dict[str, Any]) -> None:
        """Muestra los atributos de un nodo.

        Args:
            node: dict con 'id' y 'attrs'.
        """
        self._card.set_visibility(True)
        self._title.set_text(f"Nodo: {node.get('id', '')[:30]}")
        self._content.clear()
        attrs = node.get("attrs", {})
        with self._content:
            _render_attrs(attrs)

    def show_edge(self, edge: dict[str, Any]) -> None:
        """Muestra los atributos de una arista.

        Args:
            edge: dict con 'id', 'src', 'dst' y 'attrs'.
        """
        self._card.set_visibility(True)
        label = edge.get("attrs", {}).get("label", edge.get("id", ""))
        self._title.set_text(f"Arista: {label}")
        self._content.clear()
        with self._content:
            ui.label(f"Origen: {edge.get('src', '')}").style(
                "font-size:0.85em;"
            )
            ui.label(f"Destino: {edge.get('dst', '')}").style(
                "font-size:0.85em;"
            )
            _render_attrs(edge.get("attrs", {}))

    def clear(self) -> None:
        """Oculta el panel."""
        self._card.set_visibility(False)
        self._content.clear()


def _render_attrs(attrs: dict[str, Any]) -> None:
    """Renderiza pares clave-valor dentro del panel.

    Args:
        attrs: atributos del nodo o arista.
    """
    for key, value in attrs.items():
        if value is None:
            continue
        ui.label(f"{key}: {value}").style(
            "font-size:0.82em;word-break:break-all;"
        )
