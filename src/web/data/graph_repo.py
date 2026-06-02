"""
Capa de acceso a Neo4j para la página /graph.

Responsabilidades de este módulo:
  - Mantener un driver singleton (crear el driver es caro: pool de conexiones TCP).
  - ``fetch_graph`` – consulta el grafo con los filtros del panel lateral.
  - ``fetch_neighbors`` – devuelve un nodo y todos sus vecinos directos.
  - ``build_where`` – construye cláusulas WHERE con parámetros namespaced.
  - ``distinct_values`` / ``distinct_rel_types`` – valores únicos cacheados.
"""

from __future__ import annotations

import functools
from typing import Any

import structlog
from neo4j import Driver, GraphDatabase

from src.config import settings
from src.web.theme import EDGE_COLOR, node_color

log = structlog.get_logger()

# Allowlist de campos filtrables. Impide inyección Cypher en distinct_values.
_ALLOWED_FILTER_FIELDS: frozenset[str] = frozenset(
    {
        "vigente",
        "rango",
        "estatus_derogacion",
        "estatus_anulacion",
        "vigencia_agotada",
        "estado_consolidacion",
    }
)

_MAX_NODES = 30_000
_MAX_EDGES = 60_000
_MAX_NEIGHBORS = 500

_PROPERTY_FILTERS: frozenset[str] = frozenset(
    {
        "vigente",
        "rango",
        "anyo_desde",
        "anyo_hasta",
        "estatus_derogacion",
        "estatus_anulacion",
        "vigencia_agotada",
        "estado_consolidacion",
    }
)

_driver: Driver | None = None


def _get_driver() -> Driver:
    """Devuelve el driver Neo4j singleton del módulo (inicialización perezosa).

    Returns:
        Driver Neo4j configurado con las credenciales de settings.
    """
    global _driver  # noqa: PLW0603
    if _driver is None:
        _driver = GraphDatabase.driver(
            settings.neo4j.uri,
            auth=(settings.neo4j.user, settings.neo4j.password),
        )
    return _driver


def build_where(alias: str, filters: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Construye una cláusula WHERE parametrizada para el alias Cypher dado.

    Args:
        alias: Alias Cypher del nodo (e.g. ``"a"``).
        filters: Filtros activos del panel.

    Returns:
        Tupla ``(cláusula WHERE o "", dict de parámetros)``.
    """
    clauses: list[str] = []
    params: dict[str, Any] = {}

    if "vigente" in filters:
        p = f"p_{alias}_vigente"
        clauses.append(f"{alias}.vigente = ${p}")
        params[p] = filters["vigente"]

    if "rango" in filters:
        p = f"p_{alias}_rango"
        clauses.append(f"toLower({alias}.rango) CONTAINS toLower(${p})")
        params[p] = filters["rango"]

    if "anyo_desde" in filters:
        p = f"p_{alias}_anyo_desde"
        clauses.append(f"{alias}.fecha_publicacion >= ${p}")
        params[p] = f"{filters['anyo_desde']}-01-01"

    if "anyo_hasta" in filters:
        p = f"p_{alias}_anyo_hasta"
        clauses.append(f"{alias}.fecha_publicacion <= ${p}")
        params[p] = f"{filters['anyo_hasta']}-12-31"

    for field in (
        "estatus_derogacion",
        "estatus_anulacion",
        "vigencia_agotada",
        "estado_consolidacion",
    ):
        if field in filters:
            p = f"p_{alias}_{field}"
            clauses.append(f"toLower({alias}.{field}) = toLower(${p})")
            params[p] = filters[field]

    where_str = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where_str, params


def _matches_properties(node: dict[str, Any], filters: dict[str, Any]) -> bool:
    """Indica si un nodo cumple los filtros de propiedad activos.

    Los nodos UserQuery no tienen propiedades de Norma: su visibilidad se
    controla solo con ``show_userquery``, así que siempre pasan este filtro.

    Args:
        node: Nodo en formato sigma_bridge (incluye la clave ``attrs``).
        filters: Filtros activos del panel.

    Returns:
        True si el nodo debe mostrarse según los filtros de propiedad.
    """
    if node["kind"] == "UserQuery":
        return True
    attrs = node["attrs"]

    if "vigente" in filters and attrs.get("vigente") != filters["vigente"]:
        return False
    if "rango" in filters and filters["rango"].lower() not in str(attrs.get("rango") or "").lower():
        return False

    fecha = str(attrs.get("fecha_publicacion") or "")
    if "anyo_desde" in filters and fecha < f"{filters['anyo_desde']}-01-01":
        return False
    if "anyo_hasta" in filters and (not fecha or fecha > f"{filters['anyo_hasta']}-12-31"):
        return False

    for field in (
        "estatus_derogacion",
        "estatus_anulacion",
        "vigencia_agotada",
        "estado_consolidacion",
    ):
        if field in filters and str(attrs.get(field) or "").lower() != str(filters[field]).lower():
            return False
    return True


def _postprocess(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    filters: dict[str, Any],
    *,
    apply_properties: bool,
) -> dict[str, Any]:
    """Aplica los filtros del panel a un grafo crudo y lo acota a los límites duros.

    Compartido por las dos rutas de ``fetch_graph`` (búsqueda por id y grafo
    completo) para que la visibilidad de nodos, los tipos de arista y las
    propiedades se comporten igual en ambas.

    Args:
        nodes: Nodos crudos en formato sigma_bridge.
        edges: Aristas crudas en formato sigma_bridge.
        filters: Filtros activos del panel.
        apply_properties: Si True, filtra nodos Norma/Stub por propiedades en
            Python (la ruta de búsqueda no las pre-filtra en Cypher).

    Returns:
        Dict ``{"nodes": [...], "edges": [...]}`` filtrado y acotado.
    """
    visible_kinds = {
        "Norma": filters.get("show_norma", True),
        "Stub": filters.get("show_stub", True),
        "UserQuery": filters.get("show_userquery", True),
    }
    edge_types: list[str] | None = filters.get("edge_types")

    kept: dict[str, dict[str, Any]] = {}
    for node in nodes:
        if not visible_kinds.get(node["kind"], True):
            continue
        if apply_properties and not _matches_properties(node, filters):
            continue
        kept[node["id"]] = node

    if edge_types is not None:
        edges = [e for e in edges if e["type"] in edge_types]

    visible = set(kept.keys())
    edges = [e for e in edges if e["src"] in visible and e["dst"] in visible]

    if len(kept) > _MAX_NODES:
        kept = dict(list(kept.items())[:_MAX_NODES])
        visible = set(kept.keys())
        edges = [e for e in edges if e["src"] in visible and e["dst"] in visible]
    if len(edges) > _MAX_EDGES:
        edges = edges[:_MAX_EDGES]

    return {"nodes": list(kept.values()), "edges": edges}


def _node_dict(node: Any, kind: str) -> dict[str, Any]:
    """Convierte un nodo Neo4j al formato que espera ``sigma_bridge.js``.

    Un nodo se considera *stub* cuando sus propiedades no-nulas se reducen
    solo al campo ``id``: ha sido referenciado pero no ingestado completamente.

    Args:
        node: Objeto ``Node`` del driver Python de Neo4j.
        kind: Etiqueta del nodo (``"Norma"`` o ``"UserQuery"``).

    Returns:
        Dict con ``id``, ``label``, ``color``, ``kind`` y ``attrs``.
    """
    nd = dict(node)
    node_id: str = nd.get("id") or nd.get("id_nodo") or nd.get("query", "")[:40] or ""
    label: str = (nd.get("titulo") or nd.get("user_prompt") or nd.get("query") or node_id)[:60]

    non_null_keys = {k for k, v in nd.items() if v is not None and v != ""}
    effective_kind = "Stub" if non_null_keys <= {"id"} else kind

    return {
        "id": node_id,
        "label": label,
        "color": node_color(effective_kind),
        "kind": effective_kind,
        "attrs": nd,
    }


def _node_kind_from_labels(labels: list[str]) -> str:
    """Determina el kind de un nodo a partir de sus etiquetas Neo4j.

    Args:
        labels: Lista de etiquetas del nodo.

    Returns:
        ``"UserQuery"`` si está entre las etiquetas, ``"Norma"`` en caso contrario.
    """
    return "UserQuery" if "UserQuery" in labels else "Norma"


def fetch_neighbors(node_id: str, direction: str = "both") -> dict[str, Any]:
    """Devuelve el nodo con el id dado y sus vecinos directos según la dirección.

    Args:
        node_id: Identificador del nodo central (campo ``id`` o ``id_nodo``).
        direction: ``"both"`` (ambas), ``"in"`` (entrantes) o ``"out"`` (salientes).

    Returns:
        Dict ``{"nodes": [...], "edges": [...]}`` listo para ``initSigma()``.
    """
    match_pattern = {
        "in": "(n)<-[r]-(nb)",
        "out": "(n)-[r]->(nb)",
    }.get(direction, "(n)-[r]-(nb)")

    driver = _get_driver()
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    try:
        with driver.session(database=settings.neo4j.database) as session:
            result = session.run(
                f"""
                MATCH (n) WHERE n.id = $nid OR n.id_nodo = $nid
                WITH n LIMIT 1
                OPTIONAL MATCH {match_pattern}
                RETURN
                    n, labels(n) AS n_labels,
                    nb, labels(nb) AS nb_labels,
                    type(r) AS rel_type, properties(r) AS rel_attrs,
                    CASE WHEN r IS NOT NULL THEN startNode(r) ELSE null END AS start_n,
                    CASE WHEN r IS NOT NULL THEN endNode(r) ELSE null END AS end_n
                LIMIT $lim
                """,
                nid=node_id,
                lim=_MAX_NEIGHBORS,
            )
            for record in result:
                n_kind = _node_kind_from_labels(list(record["n_labels"] or []))
                n_dict = _node_dict(record["n"], n_kind)
                nodes[n_dict["id"]] = n_dict

                if record["nb"] is not None:
                    nb_kind = _node_kind_from_labels(list(record["nb_labels"] or []))
                    nb_dict = _node_dict(record["nb"], nb_kind)
                    nodes[nb_dict["id"]] = nb_dict

                    start = record["start_n"]
                    end = record["end_n"]
                    if start is not None and end is not None:
                        s, e = dict(start), dict(end)
                        src_id = s.get("id") or s.get("id_nodo") or ""
                        dst_id = e.get("id") or e.get("id_nodo") or ""
                        if src_id and dst_id:
                            edges.append(
                                {
                                    "src": src_id,
                                    "dst": dst_id,
                                    "type": record["rel_type"] or "",
                                    "color": EDGE_COLOR,
                                    "attrs": dict(record["rel_attrs"] or {}),
                                }
                            )
    except Exception as exc:  # noqa: BLE001
        log.warning("fetch_neighbors_failed", node_id=node_id, error=str(exc))

    return {"nodes": list(nodes.values()), "edges": edges}


def _query_norma_edges(
    session: Any, filters: dict[str, Any]
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Consulta las aristas Norma→Norma aplicando los filtros de propiedad en Cypher.

    Args:
        session: Sesión Neo4j abierta.
        filters: Filtros activos del panel (se traducen a WHERE sobre ``a``).

    Returns:
        Tupla ``(nodes_por_id, edges)`` en formato sigma_bridge.
    """
    where_str, params = build_where("a", filters)
    q = (
        f"MATCH (a:Norma)-[r]->(b:Norma) {where_str} "
        f"RETURN a, b, type(r) AS rel_type, properties(r) AS rel_attrs "
        f"LIMIT {_MAX_EDGES}"
    )
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    for record in session.run(q, **params):
        a_dict = _node_dict(record["a"], "Norma")
        b_dict = _node_dict(record["b"], "Norma")
        nodes[a_dict["id"]] = a_dict
        nodes[b_dict["id"]] = b_dict
        edges.append(
            {
                "src": a_dict["id"],
                "dst": b_dict["id"],
                "type": record["rel_type"],
                "color": EDGE_COLOR,
                "attrs": dict(record["rel_attrs"] or {}),
            }
        )
    return nodes, edges


def _query_isolated_norma(
    session: Any, filters: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """Consulta nodos Norma sin ninguna relación que cumplan los filtros.

    Args:
        session: Sesión Neo4j abierta.
        filters: Filtros activos del panel.

    Returns:
        Dict ``{id: node_dict}`` de nodos aislados en formato sigma_bridge.
    """
    where_str, params = build_where("n", filters)
    isolated_cond = "NOT (n)-[]-() "
    if where_str:
        q = f"MATCH (n:Norma) {where_str} AND {isolated_cond} RETURN n LIMIT {_MAX_NODES}"
    else:
        q = f"MATCH (n:Norma) WHERE {isolated_cond} RETURN n LIMIT {_MAX_NODES}"
    nodes: dict[str, dict[str, Any]] = {}
    for record in session.run(q, **params):
        n_dict = _node_dict(record["n"], "Norma")
        nodes[n_dict["id"]] = n_dict
    return nodes


def _query_userquery_edges(
    session: Any,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Consulta los nodos UserQuery y sus aristas RESULT_EDGE hacia Norma.

    Args:
        session: Sesión Neo4j abierta.

    Returns:
        Tupla ``(nodes_por_id, edges)`` en formato sigma_bridge.
    """
    q = (
        "MATCH (u:UserQuery) "
        "OPTIONAL MATCH (u)-[r:RESULT_EDGE]->(n:Norma) "
        f"RETURN u, n, type(r) AS rel_type, properties(r) AS rel_attrs "
        f"LIMIT {_MAX_EDGES}"
    )
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    for record in session.run(q):
        u_dict = _node_dict(record["u"], "UserQuery")
        nodes[u_dict["id"]] = u_dict
        if record["n"] is not None:
            n_dict = _node_dict(record["n"], "Norma")
            nodes[n_dict["id"]] = n_dict
            edges.append(
                {
                    "src": u_dict["id"],
                    "dst": n_dict["id"],
                    "type": record["rel_type"] or "RESULT_EDGE",
                    "color": EDGE_COLOR,
                    "attrs": dict(record["rel_attrs"] or {}),
                }
            )
    return nodes, edges


def fetch_graph(filters: dict[str, Any]) -> dict[str, Any]:
    """Consulta Neo4j y devuelve ``{nodes, edges}`` en formato sigma_bridge.

    Si ``filters["search_id"]`` está presente, delega en ``fetch_neighbors``.
    En caso contrario, consulta según la visibilidad de tipos de nodo y aplica
    filtros de propiedades y de tipo de arista.

    Args:
        filters: Dict con las siguientes claves opcionales:
            - ``search_id``: str – busca ese nodo y sus vecinos.
            - ``show_norma``: bool – incluir nodos Norma (default True).
            - ``show_stub``: bool – incluir nodos Stub (default True).
            - ``show_userquery``: bool – incluir nodos UserQuery (default True).
            - ``isolated_only``: bool – mostrar solo nodos sin ninguna relación.
            - ``edge_types``: list[str] | None – tipos de arista permitidos;
              None = todos, [] = ninguno.
            - ``vigente``, ``rango``, ``anyo_desde``, ``anyo_hasta``,
              ``estatus_derogacion``, ``estatus_anulacion``,
              ``vigencia_agotada``, ``estado_consolidacion``: filtros de Norma.

    Returns:
        Dict ``{"nodes": [...], "edges": [...]}`` listo para ``initSigma()``.
    """
    search_id = (filters.get("search_id") or "").strip()
    if search_id:
        raw = fetch_neighbors(search_id)
        return _postprocess(raw["nodes"], raw["edges"], filters, apply_properties=True)

    show_norma: bool = filters.get("show_norma", True)
    show_stub: bool = filters.get("show_stub", True)
    show_userquery: bool = filters.get("show_userquery", True)
    isolated_only: bool = filters.get("isolated_only", False)
    edge_types: list[str] | None = filters.get("edge_types")  # None = all

    driver = _get_driver()
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    try:
        with driver.session(database=settings.neo4j.database) as session:
            if show_norma or show_stub:
                if not isolated_only and edge_types != []:
                    n, e = _query_norma_edges(session, filters)
                    nodes.update(n)
                    edges.extend(e)
                if isolated_only or bool(_PROPERTY_FILTERS & filters.keys()):
                    nodes.update(_query_isolated_norma(session, filters))
            if show_userquery and not isolated_only and edge_types != []:
                n, e = _query_userquery_edges(session)
                nodes.update(n)
                edges.extend(e)
    except Exception as exc:  # noqa: BLE001
        log.warning("graph_query_failed", error=str(exc))

    # Las propiedades ya se pre-filtraron en Cypher (build_where) → apply_properties=False.
    return _postprocess(list(nodes.values()), edges, filters, apply_properties=False)


@functools.lru_cache(maxsize=1)
def distinct_rel_types() -> list[str]:
    """Devuelve los tipos de relación distintos existentes en la base de datos.

    Cacheado con ``lru_cache``; se invalida solo al reiniciar el servidor.

    Returns:
        Lista ordenada de strings con los tipos de relación encontrados.
        Devuelve una lista de tipos conocidos como fallback si Neo4j falla.
    """
    driver = _get_driver()
    try:
        with driver.session(database=settings.neo4j.database) as session:
            result = session.run(
                "MATCH ()-[r]->() RETURN DISTINCT type(r) AS t ORDER BY t LIMIT 50"
            )
            types = [record["t"] for record in result]
            return types if types else ["CITA", "DEROGA", "MODIFICA", "RESULT_EDGE"]
    except Exception as exc:  # noqa: BLE001
        log.warning("distinct_rel_types_failed", error=str(exc))
        return ["CITA", "DEROGA", "MODIFICA", "RESULT_EDGE"]


@functools.lru_cache(maxsize=32)
def distinct_values(field: str) -> list[str]:
    """Devuelve los valores distintos de una propiedad de Norma, cacheados.

    Args:
        field: Nombre de la propiedad. Debe estar en ``_ALLOWED_FILTER_FIELDS``.

    Returns:
        Lista ordenada de strings con los valores distintos encontrados.

    Raises:
        ValueError: Si el campo no está en ``_ALLOWED_FILTER_FIELDS``.
    """
    if field not in _ALLOWED_FILTER_FIELDS:
        raise ValueError(f"Campo '{field}' no permitido en filtros.")
    driver = _get_driver()
    try:
        with driver.session(database=settings.neo4j.database) as session:
            result = session.run(
                f"MATCH (n:Norma) WHERE n.{field} IS NOT NULL "  # noqa: S608
                f"RETURN DISTINCT n.{field} AS v ORDER BY v LIMIT 200"
            )
            return [str(record["v"]) for record in result]
    except Exception as exc:  # noqa: BLE001
        log.warning("distinct_values_failed", field=field, error=str(exc))
        return []
