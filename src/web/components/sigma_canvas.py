"""
Componente NiceGUI que envuelve el canvas de Sigma.js.

Monta un div con id 'sigma-canvas', inicializa Sigma vía sigma_bridge.js
y sondea los eventos de click cada 500 ms para devolverlos a Python.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Coroutine
from typing import Any

from nicegui import ui


class SigmaCanvas:
    """Wrapper NiceGUI alrededor del canvas Sigma.js.

    Args:
        on_node_click: corrutina llamada con {id, attrs} cuando se clica un nodo.
        on_edge_click: corrutina llamada con {id, src, dst, attrs} al clicar arista.
        height: altura del canvas en píxeles.
    """

    def __init__(
        self,
        on_node_click: Callable[[dict[str, Any]], Coroutine[Any, Any, None]]
        | None = None,
        on_edge_click: Callable[[dict[str, Any]], Coroutine[Any, Any, None]]
        | None = None,
        height: int = 600,
    ) -> None:
        self._on_node_click = on_node_click
        self._on_edge_click = on_edge_click
        self._last_click_key: str = ""

        with ui.element("div").style(
            f"width:100%;height:{height}px;position:relative;background:#1a1a2e;"
        ):
            ui.html(
                '<div id="sigma-canvas" style="width:100%;height:100%;"></div>'
            )

        self._timer = ui.timer(0.5, self._poll_clicks)

    async def _poll_clicks(self) -> None:
        """Sondea window.getLastClick() para detectar clicks desde JS."""
        result: dict[str, Any] | None = await ui.run_javascript(
            "return window.getLastClick ? window.getLastClick() : null",
            timeout=1.0,
        )
        if not result:
            return

        node = result.get("node")
        edge = result.get("edge")
        click_key = json.dumps(result, sort_keys=True, default=str)

        if click_key == self._last_click_key or (not node and not edge):
            return
        self._last_click_key = click_key

        if node and self._on_node_click:
            await self._on_node_click(node)
        elif edge and self._on_edge_click:
            await self._on_edge_click(edge)

    async def load_graph(self, graph_data: dict[str, Any]) -> None:
        """Envía datos al canvas Sigma.js.

        Args:
            graph_data: dict con 'nodes' y 'edges' en formato sigma_bridge.
        """
        payload = json.dumps(graph_data, ensure_ascii=False, default=str)
        await ui.run_javascript(
            f"window.initSigma && window.initSigma({payload})", timeout=5.0
        )

    def stop(self) -> None:
        """Detiene el timer de sondeo."""
        self._timer.cancel()
