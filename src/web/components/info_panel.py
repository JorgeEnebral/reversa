"""
Panel lateral derecho con la información del nodo o arista seleccionado.

Se activa al clicar en el grafo (el evento llega desde ``sigma_canvas.py``
vía sondeo de ``window.getLastClick()``) y se oculta con el botón ✕.
Permanece oculto hasta el primer click para no ocupar espacio innecesario
cuando el usuario solo está explorando visualmente el grafo.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from datetime import datetime
from typing import Any

from nicegui import ui

# Orden de visualización por tipo de nodo.
_NORMA_FIELD_ORDER: list[str] = [
    "vigente",
    "fecha_disposicion",
    "fecha_publicacion",
    "fecha_vigencia",
    "rango",
    "numero_oficial",
    "titulo",
    "vigencia_agotada",
    "estatus_derogacion",
    "estatus_anulacion",
    "estado_consolidacion",
]

_USERQUERY_FIELD_ORDER: list[str] = [
    "user_id",
    "user_prompt",
    "answer",
    "bbdd_query",
    "ts",
]

_FIELD_ORDER_BY_KIND: dict[str, list[str]] = {
    "Norma": _NORMA_FIELD_ORDER,
    "Stub": _NORMA_FIELD_ORDER,
    "UserQuery": _USERQUERY_FIELD_ORDER,
}

# Campos internos de Sigma que no son datos de negocio.
_SIGMA_EDGE_KEYS: frozenset[str] = frozenset({"label", "size", "color", "type"})


class InfoPanel:
    """Panel de detalle de nodo o arista seleccionado en el grafo.

    Args:
        width: Ancho del panel en píxeles.
        on_show_neighbors: Corrutina opcional llamada con el dict del nodo
            al pulsar «Mostrar vecinos».
    """

    def __init__(
        self,
        width: int = 400,
        on_show_neighbors: Callable[[dict[str, Any], str], Coroutine[Any, Any, None]] | None = None,
    ) -> None:
        self._on_show_neighbors = on_show_neighbors
        with ui.card().style(
            f"width:{width}px;height:100%;overflow-y:auto;"
            "background:var(--surface);color:var(--text);"
            "border-left:1px solid var(--border);border-radius:0;"
            "box-shadow:none;padding:16px;"
        ) as self._card:
            with ui.row().classes("w-full justify-between items-center"):
                self._title = ui.label("Selecciona un elemento").style(
                    "font-weight:700;font-size:1.05em;color:var(--text);word-break:break-all;"
                )
                ui.button("✕", on_click=self.clear).props("flat dense").style(
                    "color:var(--text-muted);flex-shrink:0;"
                )
            self._content = ui.column().classes("w-full gap-1")
        self._card.set_visibility(False)

    def show_node(self, node: dict[str, Any]) -> None:
        """Muestra los atributos de un nodo en el panel.

        El título es siempre el id del nodo. Los campos se presentan en el
        orden definido por ``_FIELD_ORDER_BY_KIND`` según el tipo de nodo.

        Args:
            node: Dict con ``"id"``, ``"kind"``, ``"label"`` y ``"attrs"``.
        """
        node_id: str = node.get("id", "")
        self._card.set_visibility(True)
        self._title.set_text(node_id)
        self._content.clear()
        with self._content:
            kind = node.get("kind", "")
            if kind:
                _kv("Tipo", kind)
            _kv("id", node_id)

            attrs = node.get("attrs", {})
            shown: set[str] = {"id", "id_nodo"}  # id_nodo ya se muestra como "id"
            field_order = _FIELD_ORDER_BY_KIND.get(kind, _NORMA_FIELD_ORDER)
            for key in field_order:
                val = attrs.get(key)
                if val is not None:
                    _kv(key, val)
                    shown.add(key)
            for k, v in attrs.items():
                if k not in shown and v is not None and not k.endswith("_codigo"):
                    _kv(k, v)

            if self._on_show_neighbors:
                captured = dict(node)
                with ui.row().style("margin-top:10px;gap:4px;flex-wrap:wrap;"):
                    for label, direction in [
                        ("Vecinos", "both"),
                        ("Entrantes", "in"),
                        ("Salientes", "out"),
                    ]:
                        ui.button(
                            label,
                            on_click=lambda n=captured, d=direction: self._on_show_neighbors(n, d),
                        ).props("flat dense").style("color:var(--brand);font-size:0.85em;")

    def show_edge(self, edge: dict[str, Any]) -> None:
        """Muestra los atributos de una arista en el panel.

        Muestra tipo, atributos de negocio, nodo origen y nodo destino.

        Args:
            edge: Dict con ``"type"``, ``"src"``, ``"dst"`` y ``"attrs"``.
        """
        edge_type: str = edge.get("type", "")
        self._card.set_visibility(True)
        self._title.set_text(f"Arista: {edge_type}")
        self._content.clear()
        with self._content:
            _kv("Tipo", edge_type)
            for k, v in edge.get("attrs", {}).items():
                if v is not None and not k.endswith("_codigo") and k not in _SIGMA_EDGE_KEYS:
                    _kv(k, v)
            _kv("Origen", edge.get("src", ""))
            _kv("Destino", edge.get("dst", ""))

    def clear(self) -> None:
        """Oculta el panel y limpia su contenido."""
        self._card.set_visibility(False)
        self._content.clear()


def _format_ts(raw: Any) -> str:
    """Formatea un timestamp Neo4j como ``DD-MM-AAAA : HH:MM:SS``.

    Args:
        raw: Valor del campo ``ts`` (string ISO serializado por el driver Neo4j).

    Returns:
        Timestamp formateado o el valor original como string si no se puede parsear.
    """
    s = str(raw)
    try:
        dt = datetime.fromisoformat(s[:19].replace(" ", "T"))
        return dt.strftime("%d-%m-%Y : %H:%M:%S")
    except ValueError:
        return s


def _kv(key: str, value: Any) -> None:
    """Renderiza un par clave-valor con la clave en negrita.

    Aplica formato especial al campo ``ts`` (timestamp).

    Args:
        key: Nombre del campo (en negrita).
        value: Valor a mostrar.
    """
    display = _format_ts(value) if key == "ts" else str(value)
    ui.html(f'<span style="font-weight:700;">{key}:</span><span> {display}</span>').style(
        "font-size:0.92em;word-break:break-all;display:block;"
    )
