"""
Panel lateral izquierdo de filtros del grafo.

Genera campos de filtro a partir del esquema :Norma de la ontología semántica
y gestiona el estado de los filtros activos.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from nicegui import ui


class FilterPanel:
    """Sidebar de filtros para la página /graph.

    Genera inputs según el tipo del atributo y llama al callback
    on_apply con el dict de filtros activos.

    Args:
        on_apply: corrutina llamada con {campo: valor} al pulsar Aplicar.
        width: ancho del panel en píxeles.
    """

    def __init__(
        self,
        on_apply: Callable[[dict[str, Any]], Coroutine[Any, Any, None]],
        width: int = 220,
    ) -> None:
        self._on_apply = on_apply
        self._filters: dict[str, Any] = {}  # noqa: RUF012

        with ui.card().style(
            f"width:{width}px;height:100%;overflow-y:auto;"
            "background:#1e1e3f;color:#e0e0e0;padding:12px;"
        ):
            ui.label("Filtros").style(
                "font-weight:bold;font-size:1.1em;margin-bottom:8px;"
            )
            self._build_filters()

            with ui.row().classes("w-full gap-2 mt-4"):
                ui.button("Restablecer", on_click=self._reset).props(
                    "flat dense"
                ).style("color:#e0e0e0;flex:1;")
                ui.button("Aplicar", on_click=self._apply).style("flex:1;")

    def _build_filters(self) -> None:
        """Construye los campos de filtro."""
        # Vigente
        ui.label("Vigente").style("font-size:0.85em;margin-top:8px;")
        self._vigente = ui.select(["Todas", "Sí", "No"], value="Todas").style(
            "width:100%;"
        )

        # Rango
        ui.label("Rango").style("font-size:0.85em;margin-top:8px;")
        self._rango = ui.input(placeholder="ej. Ley").style("width:100%;")

        # Departamento
        ui.label("Departamento").style("font-size:0.85em;margin-top:8px;")
        self._departamento = ui.input(
            placeholder="ej. Jefatura del Estado"
        ).style("width:100%;")

        # Fecha publicación
        ui.label("Año publicación").style("font-size:0.85em;margin-top:8px;")
        self._anyo_desde = ui.number(
            placeholder="Desde", min=1950, max=2030
        ).style("width:100%;")
        self._anyo_hasta = ui.number(
            placeholder="Hasta", min=1950, max=2030
        ).style("width:100%;")

    async def _apply(self) -> None:
        """Recopila el estado de los controles y llama on_apply."""
        filters: dict[str, Any] = {}  # type: ignore[misc]

        vigente_val = self._vigente.value
        if vigente_val == "Sí":
            filters["vigente"] = True
        elif vigente_val == "No":
            filters["vigente"] = False

        if self._rango.value:
            filters["rango"] = self._rango.value.strip()
        if self._departamento.value:
            filters["departamento"] = self._departamento.value.strip()
        if self._anyo_desde.value:
            filters["anyo_desde"] = int(self._anyo_desde.value)
        if self._anyo_hasta.value:
            filters["anyo_hasta"] = int(self._anyo_hasta.value)

        self._filters = filters
        await self._on_apply(filters)

    def _reset(self) -> None:
        """Restablece todos los filtros a su valor por defecto."""
        self._vigente.value = "Todas"
        self._rango.value = ""
        self._departamento.value = ""
        self._anyo_desde.value = None
        self._anyo_hasta.value = None
        self._filters = {}
