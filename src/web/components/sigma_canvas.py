"""
Componente NiceGUI que envuelve el canvas de Sigma.js.

Diseño del contenedor
---------------------
El canvas usa ``position:absolute; inset:0`` en lugar de ``height:100%``
porque NiceGUI envuelve ``ui.html(...)`` en un ``<div class="nicegui-html">``
cuya altura es ``auto`` (0 si el contenido está fuera del flujo). La cadena
``height:100%`` se rompería ahí. Con ``position:absolute; inset:0`` el div
se ancla directamente al ancestro ``position:relative`` más cercano (la
columna central de ``graph.py``), cuya altura sí está definida en píxeles.

Detección de clicks
-------------------
Los eventos JS→Python se gestionan por sondeo (``ui.timer`` cada 500 ms)
en lugar de ``emitEvent`` por simplicidad: el flujo ``emitEvent → ui.on``
requiere que el websocket esté establecido en el momento del click, mientras
que el sondeo es tolerante a reconexiones. La latencia de 500 ms es
imperceptible en un grafo de exploración.

Ciclo de vida del timer
-----------------------
El timer se cancela automáticamente cuando el cliente desaparece (navegación,
recarga, cierre de pestaña). Si ``run_javascript`` lanza ``RuntimeError``
(cliente eliminado) o ``TimeoutError``, el timer se detiene para evitar el
aviso «Client has been deleted but is still being used».
"""

from __future__ import annotations

import json
from collections.abc import Callable, Coroutine
from typing import Any

from nicegui import ui


class SigmaCanvas:
    """Wrapper NiceGUI alrededor del canvas Sigma.js.

    Renderiza el div contenedor de Sigma, le envía payloads de grafo vía
    ``window.initSigma(graphData)`` y sondea clicks para devolverlos a Python.

    Args:
        on_node_click: Corrutina llamada con ``{id, kind, label, attrs}`` al clicar un nodo.
        on_edge_click: Corrutina llamada con ``{id, src, dst, type, attrs}`` al clicar arista.
    """

    def __init__(
        self,
        on_node_click: Callable[[dict[str, Any]], Coroutine[Any, Any, None]] | None = None,
        on_edge_click: Callable[[dict[str, Any]], Coroutine[Any, Any, None]] | None = None,
    ) -> None:
        self._on_node_click = on_node_click
        self._on_edge_click = on_edge_click
        # Clave del último click procesado; evita disparar el callback dos veces
        # cuando el sondeo ocurre antes de que el usuario haga click de nuevo.
        self._last_click_key: str = ""

        # El ancestro position:relative es la columna central definida en graph.py.
        # inset:0 equivale a top:0; right:0; bottom:0; left:0.
        ui.html('<div id="sigma-canvas" style="position:absolute;inset:0;"></div>')

        self._timer = ui.timer(0.5, self._poll_clicks)

    async def _poll_clicks(self) -> None:
        """Sondea ``window.getLastClick()`` para detectar clicks desde JS.

        ``getLastClick()`` consume el click (lo resetea a null) al leerlo,
        por lo que cada evento se procesa exactamente una vez aunque el timer
        dispare varias veces antes del siguiente click.
        """
        try:
            result: dict[str, Any] | None = await ui.run_javascript(
                "return window.getLastClick ? window.getLastClick() : null",
                timeout=1.0,
            )
        except Exception:  # noqa: BLE001
            # Cliente eliminado (navegación/recarga) o timeout: detener el timer.
            self._timer.cancel()
            return

        if not result:
            return

        node = result.get("node")
        edge = result.get("edge")
        # Serializar como clave para detectar si es el mismo evento que la vez anterior.
        click_key = json.dumps(result, sort_keys=True, default=str)

        if click_key == self._last_click_key or (not node and not edge):
            return
        self._last_click_key = click_key

        if node and self._on_node_click:
            await self._on_node_click(node)
        elif edge and self._on_edge_click:
            await self._on_edge_click(edge)

    async def load_graph(self, graph_data: dict[str, Any]) -> None:
        """Envía datos al canvas Sigma.js llamando a ``window.initSigma``.

        El payload se serializa con ``ensure_ascii=True`` para escapar caracteres
        no-ASCII (incluidos U+2028/U+2029, ilegales en literales de string JS),
        garantizando que el JSON embebido en el script sea siempre JS válido.

        Args:
            graph_data: Dict ``{"nodes": [...], "edges": [...]}`` producido por
                ``graph_repo.fetch_graph``.
        """
        try:
            payload = json.dumps(graph_data, ensure_ascii=True, default=str)
            await ui.run_javascript(
                f"window.initSigma && window.initSigma({payload})", timeout=10.0
            )
        except Exception:  # noqa: BLE001
            # Cliente eliminado entre la carga de datos y el envío JS; se ignora.
            pass

    def stop(self) -> None:
        """Detiene el timer de sondeo (p.ej. al destruir la página)."""
        self._timer.cancel()
