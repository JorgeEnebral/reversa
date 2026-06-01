"""
Panel lateral izquierdo de filtros del grafo.

El scope (alcance) se incluye en el mismo dict de filtros que se pasa a
``on_apply`` (bajo la clave ``"scope"``) en lugar de como argumento separado.
Esto permite que la firma del callback sea estable: ``Callable[[dict], Coro]``.
El receptor (``graph.py``) extrae el scope con ``.pop("scope", "norma")`` antes
de pasarlo a ``graph_repo.fetch_graph``.

Los campos ``departamento`` y ``diario`` se omiten porque sus ParseFlags están
a ``False`` en la configuración por defecto: no se cargan en Neo4j y filtrar
por ellos siempre devolvería vacío.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from nicegui import ui

# Opciones del selector de alcance → etiquetas de pantalla.
_SCOPE_OPTIONS: dict[str, str] = {
    "norma": "Legislación",
    "userquery": "Consultas",
    "all": "Todo",
}


class FilterPanel:
    """Sidebar izquierdo de filtros para la página /graph.

    Genera los controles de filtro y el selector de alcance, y llama a
    ``on_apply`` con el dict ``{scope, ...filtros_activos}`` al pulsar Aplicar.
    Solo incluye en el dict los filtros que el usuario haya rellenado
    (ausencia de clave = sin filtro, no «mostrar nada»).

    Args:
        on_apply: Corrutina llamada con el dict de filtros al pulsar Aplicar.
        width: Ancho del panel en píxeles.
    """

    def __init__(
        self,
        on_apply: Callable[[dict[str, Any]], Coroutine[Any, Any, None]],
        width: int = 220,
    ) -> None:
        self._on_apply = on_apply

        with ui.card().style(
            f"width:{width}px;height:100%;overflow-y:auto;"
            "background:var(--surface);color:var(--text);"
            "border-right:1px solid var(--border);border-radius:0;"
            "box-shadow:none;padding:16px;"
        ):
            ui.label("Filtros").style(
                "font-weight:700;font-size:1.05em;margin-bottom:8px;color:var(--text);"
            )
            self._build_filters()

            with ui.row().classes("w-full gap-2 mt-4"):
                ui.button("Restablecer", on_click=self._reset).props("flat dense").style(
                    "color:var(--text-muted);flex:1;"
                )
                ui.button("Aplicar", on_click=self._apply).props("unelevated").style(
                    "background:var(--brand);color:#fff;flex:1;"
                )

    def _build_filters(self) -> None:
        """Instancia los controles del panel en orden visual."""
        # Alcance: define qué tipos de nodo y aristas consultar.
        ui.label("Alcance").style("font-size:0.85em;margin-top:8px;color:var(--text-muted);")
        self._scope = ui.select(options=_SCOPE_OPTIONS, value="norma").style("width:100%;")

        # Vigente: tri-estado (Todas / Sí / No) porque null ≠ False en Neo4j;
        # «Todas» omite la cláusula WHERE para no excluir nodos sin el campo.
        ui.label("Vigente").style("font-size:0.85em;margin-top:8px;color:var(--text-muted);")
        self._vigente = ui.select(["Todas", "Sí", "No"], value="Todas").style("width:100%;")

        # Rango: búsqueda CONTAINS insensible a mayúsculas (build_where lo gestiona).
        ui.label("Rango").style("font-size:0.85em;margin-top:8px;color:var(--text-muted);")
        self._rango = ui.input(placeholder="ej. Ley").style("width:100%;")

        # Año publicación: par desde/hasta que se convierte a fecha ISO en build_where.
        ui.label("Año publicación").style(
            "font-size:0.85em;margin-top:8px;color:var(--text-muted);"
        )
        self._anyo_desde = ui.number(placeholder="Desde", min=1950, max=2030).style(
            "width:100%;"
        )
        self._anyo_hasta = ui.number(placeholder="Hasta", min=1950, max=2030).style(
            "width:100%;"
        )

    async def _apply(self) -> None:
        """Recopila el estado de los controles y llama ``on_apply``.

        Solo añade al dict los filtros con valor no vacío para que
        ``build_where`` pueda detectar fácilmente cuáles están activos.
        """
        filters: dict[str, Any] = {"scope": self._scope.value}

        vigente_val = self._vigente.value
        if vigente_val == "Sí":
            filters["vigente"] = True
        elif vigente_val == "No":
            filters["vigente"] = False
        # "Todas" → no se añade la clave; build_where omite la cláusula.

        if self._rango.value:
            filters["rango"] = self._rango.value.strip()
        if self._anyo_desde.value:
            filters["anyo_desde"] = int(self._anyo_desde.value)
        if self._anyo_hasta.value:
            filters["anyo_hasta"] = int(self._anyo_hasta.value)

        await self._on_apply(filters)

    def _reset(self) -> None:
        """Restablece todos los controles a su valor por defecto."""
        self._scope.value = "norma"
        self._vigente.value = "Todas"
        self._rango.value = ""
        self._anyo_desde.value = None
        self._anyo_hasta.value = None
