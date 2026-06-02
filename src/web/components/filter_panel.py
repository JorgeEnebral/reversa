"""
Panel lateral izquierdo de filtros del grafo.

Estructura
----------
La tarjeta usa flex-column con overflow:hidden. El área de filtros es un
``ui.scroll_area`` que ocupa el espacio disponible (flex:1). Los botones
«Restablecer» y «Aplicar» están fijos en la parte inferior (flex-shrink:0).

Secciones de filtros
--------------------
1. Buscar nodo: por id → carga el nodo y todos sus vecinos directos.
2. Nodos: visibilidad por tipo (Norma consolidada, Stub, UserQuery).
3. Aristas: multi-selección de tipos de relación.
4. Propiedades: vigente, rango, año publicación, estatus.
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

from nicegui import ui

from src.web.data.graph_repo import distinct_rel_types, distinct_values


class FilterPanel:
    """Sidebar izquierdo de filtros para la página /graph.

    Llama a ``on_apply`` con el dict de filtros al pulsar Aplicar.

    Args:
        on_apply: Corrutina llamada con el dict de filtros al pulsar Aplicar.
        width: Ancho del panel en píxeles.
    """

    def __init__(
        self,
        on_apply: Callable[[dict[str, Any]], Coroutine[Any, Any, None]],
        width: int = 280,
    ) -> None:
        self._on_apply = on_apply
        self._all_edge_types: list[str] = distinct_rel_types()

        with ui.card().style(
            f"width:{width}px;height:100%;overflow:hidden;"
            "display:flex;flex-direction:column;"
            "background:var(--surface);color:var(--text);"
            "border-right:1px solid var(--border);border-radius:0;"
            "box-shadow:none;padding:0;"
        ):
            with ui.scroll_area().style("flex:1;min-height:0;"):
                with ui.column().style("padding:14px;width:100%;gap:2px;"):
                    ui.label("Filtros").style(
                        "font-weight:700;font-size:1.05em;margin-bottom:6px;color:var(--text);"
                    )
                    self._build_search_section()
                    self._divider()
                    self._build_nodes_section()
                    self._divider()
                    self._build_edges_section()
                    self._divider()
                    self._build_properties_section()

            # Botones fijos en la parte inferior.
            with ui.row().style(
                "flex-shrink:0;padding:10px 14px;gap:8px;"
                "border-top:1px solid var(--border);"
                "background:var(--surface);"
                "margin-top:4px;"
            ):
                ui.button("Restablecer", on_click=self._reset).props("flat dense").style(
                    "color:var(--text-muted);flex:1;"
                )
                ui.button("Aplicar", on_click=self._apply).props("unelevated").style(
                    "background:var(--brand);color:#fff;flex:1;"
                )

    # ------------------------------------------------------------------
    # Construcción de secciones
    # ------------------------------------------------------------------

    def _divider(self) -> None:
        """Inserta un separador visual entre secciones."""
        ui.separator().style("margin:10px 0;opacity:0.4;")

    def _section_label(self, text: str) -> None:
        """Etiqueta de cabecera de sección."""
        ui.label(text).style(
            "font-size:0.8em;font-weight:700;color:var(--text-muted);"
            "text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px;"
        )

    def _build_search_section(self) -> None:
        """Sección: buscar un nodo concreto por ID."""
        self._section_label("Buscar nodo")
        self._search_id = ui.input(placeholder="ID del nodo…").style("width:100%;")

    def _build_nodes_section(self) -> None:
        """Sección: visibilidad por tipo de nodo."""
        self._section_label("Nodos")
        self._show_norma = ui.toggle({True: "Sí", False: "No"}, value=True).style(
            "margin-bottom:2px;"
        )
        ui.label("Legislación consolidada").style("font-size:0.82em;margin-bottom:6px;")

        self._show_stub = ui.toggle({True: "Sí", False: "No"}, value=True).style(
            "margin-bottom:2px;"
        )
        ui.label("Nodos stub").style("font-size:0.82em;margin-bottom:6px;")

        self._show_userquery = ui.toggle({True: "Sí", False: "No"}, value=True).style(
            "margin-bottom:2px;"
        )
        ui.label("Consultas (UserQuery)").style("font-size:0.82em;margin-bottom:6px;")

        self._isolated_only = ui.toggle({True: "Sí", False: "No"}, value=False).style(
            "margin-bottom:2px;"
        )
        ui.label("Solo nodos aislados").style("font-size:0.82em;")

    def _build_edges_section(self) -> None:
        """Sección: filtrar por tipo de arista."""
        self._section_label("Aristas")
        with ui.row().classes("items-center gap-1").style("margin-bottom:4px;"):
            ui.button(
                "Todas",
                on_click=lambda: self._set_edge_types(list(self._all_edge_types)),
            ).props("flat dense").style("font-size:0.8em;padding:0 4px;")
            ui.button(
                "Ninguna",
                on_click=lambda: self._set_edge_types([]),
            ).props("flat dense").style("font-size:0.8em;padding:0 4px;")

        self._edge_types = ui.select(
            options=self._all_edge_types,
            value=list(self._all_edge_types),
            multiple=True,
        ).style("width:100%;")

    def _build_properties_section(self) -> None:
        """Sección: filtros de propiedades de Norma."""
        self._section_label("Propiedades")

        ui.label("Vigente").style("font-size:0.82em;margin-top:4px;color:var(--text-muted);")
        self._vigente = ui.select(["Todas", "Sí", "No"], value="Todas").style("width:100%;")

        ui.label("Rango").style("font-size:0.82em;margin-top:6px;color:var(--text-muted);")
        self._rango = ui.input(placeholder="ej. Ley").style("width:100%;")

        ui.label("Año publicación").style(
            "font-size:0.82em;margin-top:6px;color:var(--text-muted);"
        )
        self._anyo_desde = ui.number(placeholder="Desde", min=1950, max=2030).style("width:100%;")
        self._anyo_hasta = ui.number(placeholder="Hasta", min=1950, max=2030).style("width:100%;")

        for field, label in [
            ("estatus_derogacion", "Estatus derogación"),
            ("estatus_anulacion", "Estatus anulación"),
            ("vigencia_agotada", "Vigencia agotada"),
            ("estado_consolidacion", "Estado consolidación"),
        ]:
            opts = distinct_values(field)
            if opts:
                ui.label(label).style("font-size:0.82em;margin-top:6px;color:var(--text-muted);")
                setattr(
                    self,
                    f"_{field}",
                    ui.select(["(todas)"] + opts, value="(todas)").style("width:100%;"),
                )
            else:
                setattr(self, f"_{field}", None)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def _set_edge_types(self, types: list[str]) -> None:
        """Selecciona todos o ningún tipo de arista en el multi-select."""
        self._edge_types.value = types

    async def _apply(self) -> None:
        """Recopila el estado de los controles y llama ``on_apply``."""
        filters: dict[str, Any] = {}

        # Buscar nodo
        sid = (self._search_id.value or "").strip()
        if sid:
            filters["search_id"] = sid

        # Visibilidad de nodos
        filters["show_norma"] = bool(self._show_norma.value)
        filters["show_stub"] = bool(self._show_stub.value)
        filters["show_userquery"] = bool(self._show_userquery.value)
        filters["isolated_only"] = bool(self._isolated_only.value)

        # Tipos de arista
        selected = list(self._edge_types.value or [])
        if set(selected) >= set(self._all_edge_types):
            filters["edge_types"] = None  # sin filtro
        else:
            filters["edge_types"] = selected

        # Vigente
        if self._vigente.value == "Sí":
            filters["vigente"] = True
        elif self._vigente.value == "No":
            filters["vigente"] = False

        # Rango
        if self._rango.value:
            filters["rango"] = self._rango.value.strip()

        # Años
        if self._anyo_desde.value:
            filters["anyo_desde"] = int(self._anyo_desde.value)
        if self._anyo_hasta.value:
            filters["anyo_hasta"] = int(self._anyo_hasta.value)

        # Estatus
        for field in (
            "estatus_derogacion",
            "estatus_anulacion",
            "vigencia_agotada",
            "estado_consolidacion",
        ):
            ctrl = getattr(self, f"_{field}", None)
            if ctrl is not None and ctrl.value and ctrl.value != "(todas)":
                filters[field] = ctrl.value

        await self._on_apply(filters)

    def _reset(self) -> None:
        """Restablece todos los controles a su valor por defecto."""
        self._search_id.value = ""
        self._show_norma.value = True
        self._show_stub.value = True
        self._show_userquery.value = True
        self._isolated_only.value = False
        self._edge_types.value = list(self._all_edge_types)
        self._vigente.value = "Todas"
        self._rango.value = ""
        self._anyo_desde.value = None
        self._anyo_hasta.value = None
        for field in (
            "estatus_derogacion",
            "estatus_anulacion",
            "vigencia_agotada",
            "estado_consolidacion",
        ):
            ctrl = getattr(self, f"_{field}", None)
            if ctrl is not None:
                ctrl.value = "(todas)"
