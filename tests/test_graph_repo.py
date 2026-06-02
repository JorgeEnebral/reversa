"""
Tests de las funciones puras de filtrado de src/web/data/graph_repo.py.

No tocan Neo4j: build_where, _matches_properties y _postprocess son puras.
Cubren la regresión por la que la búsqueda por id ignoraba el resto de filtros.
"""

from __future__ import annotations

from typing import Any

from src.web.data.graph_repo import _matches_properties, _postprocess, build_where


def _node(node_id: str, kind: str, **attrs: Any) -> dict[str, Any]:
    """Construye un nodo en formato sigma_bridge para los tests."""
    return {"id": node_id, "label": node_id, "color": "#000", "kind": kind, "attrs": attrs}


def _edge(src: str, dst: str, edge_type: str) -> dict[str, Any]:
    """Construye una arista en formato sigma_bridge para los tests."""
    return {"src": src, "dst": dst, "type": edge_type, "color": "#000", "attrs": {}}


# ── build_where ──────────────────────────────────────────────────────────────


def test_build_where_sin_filtros_devuelve_vacio() -> None:
    """Sin filtros activos no hay cláusula WHERE ni parámetros."""
    where, params = build_where("a", {})
    assert where == ""
    assert params == {}


def test_build_where_vigente_genera_clausula_parametrizada() -> None:
    """vigente produce una igualdad parametrizada con el alias en el nombre."""
    where, params = build_where("a", {"vigente": True})
    assert where == "WHERE a.vigente = $p_a_vigente"
    assert params == {"p_a_vigente": True}


def test_build_where_rango_usa_contains_case_insensitive() -> None:
    """rango usa CONTAINS sobre toLower para coincidencia parcial."""
    where, params = build_where("a", {"rango": "Ley"})
    assert "toLower(a.rango) CONTAINS toLower($p_a_rango)" in where
    assert params["p_a_rango"] == "Ley"


def test_build_where_combina_varios_filtros_con_and() -> None:
    """Varios filtros se unen con AND y cada uno aporta su parámetro."""
    where, params = build_where(
        "a", {"vigente": True, "anyo_desde": 2000, "estatus_derogacion": "N"}
    )
    assert where.startswith("WHERE ")
    assert where.count(" AND ") == 2
    assert params["p_a_anyo_desde"] == "2000-01-01"
    assert params["p_a_estatus_derogacion"] == "N"


# ── _matches_properties ──────────────────────────────────────────────────────


def test_matches_userquery_siempre_pasa() -> None:
    """UserQuery no tiene propiedades de Norma → pasa cualquier filtro."""
    node = _node("q1", "UserQuery")
    assert _matches_properties(node, {"vigente": True, "rango": "Ley"}) is True


def test_matches_vigente_coincide_y_no_coincide() -> None:
    """vigente filtra por igualdad exacta del booleano."""
    vigente = _node("n1", "Norma", vigente=True)
    assert _matches_properties(vigente, {"vigente": True}) is True
    assert _matches_properties(vigente, {"vigente": False}) is False


def test_matches_rango_es_substring_case_insensitive() -> None:
    """rango coincide como subcadena sin distinguir mayúsculas."""
    node = _node("n1", "Norma", rango="Ley Orgánica")
    assert _matches_properties(node, {"rango": "ley"}) is True
    assert _matches_properties(node, {"rango": "Decreto"}) is False


def test_matches_anyo_rango_publicacion() -> None:
    """anyo_desde/anyo_hasta acotan por fecha_publicacion."""
    node = _node("n1", "Norma", fecha_publicacion="2015-10-02")
    assert _matches_properties(node, {"anyo_desde": 2010, "anyo_hasta": 2020}) is True
    assert _matches_properties(node, {"anyo_desde": 2016}) is False
    assert _matches_properties(node, {"anyo_hasta": 2014}) is False


def test_matches_estatus_case_insensitive() -> None:
    """Los estatus comparan por igualdad sin distinguir mayúsculas."""
    node = _node("n1", "Norma", estatus_derogacion="N")
    assert _matches_properties(node, {"estatus_derogacion": "n"}) is True
    assert _matches_properties(node, {"estatus_derogacion": "S"}) is False


def test_matches_stub_se_excluye_si_hay_filtro_de_propiedad() -> None:
    """Un stub (solo id) no cumple ningún filtro de propiedad activo."""
    stub = _node("n1", "Stub")
    assert _matches_properties(stub, {"rango": "Ley"}) is False
    # Sin filtros de propiedad un stub pasa.
    assert _matches_properties(stub, {}) is True


# ── _postprocess: la regresión de búsqueda + filtros ─────────────────────────


def test_postprocess_filtra_visibilidad_de_nodos() -> None:
    """show_norma=False elimina nodos Norma y sus aristas colgantes."""
    nodes = [_node("a", "Norma"), _node("q", "UserQuery")]
    edges = [_edge("q", "a", "RESULT_EDGE")]

    out = _postprocess(nodes, edges, {"show_norma": False}, apply_properties=False)

    assert [n["id"] for n in out["nodes"]] == ["q"]
    assert out["edges"] == []  # arista colgante eliminada


def test_postprocess_filtra_tipos_de_arista() -> None:
    """edge_types restringe las aristas a los tipos seleccionados."""
    nodes = [_node("a", "Norma"), _node("b", "Norma"), _node("c", "Norma")]
    edges = [_edge("a", "b", "DEROGA"), _edge("a", "c", "CITA")]

    out = _postprocess(nodes, edges, {"edge_types": ["DEROGA"]}, apply_properties=False)

    assert [e["type"] for e in out["edges"]] == ["DEROGA"]


def test_postprocess_edge_types_none_no_filtra_aristas() -> None:
    """edge_types=None significa 'todas' → no filtra."""
    nodes = [_node("a", "Norma"), _node("b", "Norma")]
    edges = [_edge("a", "b", "DEROGA")]

    out = _postprocess(nodes, edges, {"edge_types": None}, apply_properties=False)

    assert len(out["edges"]) == 1


def test_postprocess_aplica_propiedades_en_busqueda() -> None:
    """Con apply_properties=True (ruta búsqueda) las propiedades filtran nodos.

    Reproduce el bug: buscar un id traía vecinos sin respetar el resto de filtros.
    """
    nodes = [
        _node("centro", "Norma", rango="Ley"),
        _node("vecino_ley", "Norma", rango="Ley"),
        _node("vecino_rd", "Norma", rango="Real Decreto"),
    ]
    edges = [_edge("centro", "vecino_ley", "CITA"), _edge("centro", "vecino_rd", "CITA")]

    out = _postprocess(nodes, edges, {"rango": "Ley"}, apply_properties=True)

    kept_ids = {n["id"] for n in out["nodes"]}
    assert kept_ids == {"centro", "vecino_ley"}
    assert [(e["src"], e["dst"]) for e in out["edges"]] == [("centro", "vecino_ley")]


def test_postprocess_no_aplica_propiedades_si_flag_false() -> None:
    """Con apply_properties=False las propiedades no se re-filtran en Python."""
    nodes = [_node("a", "Norma", rango="Real Decreto")]
    edges: list[dict[str, Any]] = []

    out = _postprocess(nodes, edges, {"rango": "Ley"}, apply_properties=False)

    assert [n["id"] for n in out["nodes"]] == ["a"]


def test_postprocess_combina_busqueda_con_aristas_y_propiedades() -> None:
    """Búsqueda con filtros de arista y propiedad simultáneos (caso del usuario)."""
    nodes = [
        _node("centro", "Norma", rango="Ley", vigente=True),
        _node("derogada", "Norma", rango="Ley", vigente=False),
        _node("citada", "Norma", rango="Ley", vigente=True),
    ]
    edges = [_edge("centro", "derogada", "DEROGA"), _edge("centro", "citada", "CITA")]

    out = _postprocess(
        nodes,
        edges,
        {"vigente": True, "edge_types": ["CITA"]},
        apply_properties=True,
    )

    kept_ids = {n["id"] for n in out["nodes"]}
    assert kept_ids == {"centro", "citada"}  # 'derogada' cae por vigente=False
    assert [e["type"] for e in out["edges"]] == ["CITA"]
