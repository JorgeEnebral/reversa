"""
Capa de acceso a Neo4j para la página /graph.

Responsabilidades de este módulo:
  - Mantener un driver singleton (crear el driver es caro: pool de conexiones TCP).
  - ``fetch_graph`` – consulta el grafo con estrategia *edges-first* para
    garantizar un subgrafo conexo: si consultáramos nodos primero y aristas
    después, los 25k nodos devueltos raramente compartirían aristas entre sí.
  - ``build_where`` – construye cláusulas WHERE con parámetros *namespaced*
    (``p_{alias}_{campo}``) para poder reutilizar el mismo dict de filtros con
    distintos alias Cypher sin colisiones ni string-replace frágiles.
  - ``distinct_values`` – lista de valores únicos de un campo, cacheada en
    memoria con ``lru_cache`` para no requerir una round-trip a Neo4j en cada
    renderizado del panel de filtros.
"""

from __future__ import annotations

import functools
from typing import Any, Literal

import structlog
from neo4j import Driver, GraphDatabase

from src.config import settings
from src.web.theme import EDGE_COLOR, node_color

log = structlog.get_logger()

Scope = Literal["all", "norma", "userquery"]

# Allowlist de campos filtrables. Impide inyección Cypher en distinct_values,
# que interpola el nombre del campo directamente en la query (no se puede
# parametrizar el nombre de una propiedad en Cypher).
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

# Límite de aristas por consulta. El renderer WebGL de Sigma aguanta decenas de
# miles de aristas; el cuello de botella real es la serialización JSON y la
# ejecución de ForceAtlas2 en el hilo principal del navegador.
_MAX_EDGES = 25_000

# El driver Neo4j gestiona internamente un pool de conexiones bolt. Crearlo
# una sola vez al primer uso evita la latencia de handshake en cada "Aplicar".
_driver: Driver | None = None


def _get_driver() -> Driver:
    """Devuelve el driver Neo4j singleton del módulo.

    Inicialización perezosa: el driver solo se crea cuando se hace la primera
    consulta, no al importar el módulo (evita fallos de arranque si Neo4j no
    está disponible en el momento de la importación).

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

    Usa nombres de parámetro con prefijo ``p_{alias}_campo`` en lugar de
    ``$campo`` plano. Así la misma consulta puede filtrar dos nodos con alias
    distintos (p.ej. ``a`` y ``b``) sin que sus parámetros colisionen, y sin
    recurrir al frágil ``where_str.replace('n.', 'a.')`` del código anterior.

    Args:
        alias: Alias Cypher del nodo (e.g. ``"a"``, ``"n"``).
        filters: Filtros activos del panel. La clave ``"scope"`` ya debe haber
            sido extraída antes de llamar a esta función.

    Returns:
        Tupla ``(cláusula WHERE completa o "", dict de parámetros)``.
        Si no hay filtros activos, devuelve ``("", {})``.
    """
    clauses: list[str] = []
    params: dict[str, Any] = {}

    if "vigente" in filters:
        # vigente es boolean en Neo4j; comparación exacta, sin CONTAINS.
        p = f"p_{alias}_vigente"
        clauses.append(f"{alias}.vigente = ${p}")
        params[p] = filters["vigente"]

    if "rango" in filters:
        # Búsqueda insensible a mayúsculas; el usuario escribe "ley" y encuentra "Ley".
        p = f"p_{alias}_rango"
        clauses.append(f"toLower({alias}.rango) CONTAINS toLower(${p})")
        params[p] = filters["rango"]

    if "anyo_desde" in filters:
        # fecha_publicacion se almacena como string "YYYY-MM-DD"; la comparación
        # lexicográfica funciona porque el formato ISO-8601 es ordenable.
        p = f"p_{alias}_anyo_desde"
        clauses.append(f"{alias}.fecha_publicacion >= ${p}")
        params[p] = f"{filters['anyo_desde']}-01-01"

    if "anyo_hasta" in filters:
        p = f"p_{alias}_anyo_hasta"
        clauses.append(f"{alias}.fecha_publicacion <= ${p}")
        params[p] = f"{filters['anyo_hasta']}-12-31"

    where_str = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where_str, params


def _node_dict(node: Any, kind: str) -> dict[str, Any]:
    """Convierte un nodo Neo4j al formato que espera ``sigma_bridge.js``.

    El campo ``color`` se asigna aquí en Python (desde ``theme.py``) para que
    el JS no necesite conocer la lógica de colores ni hardcodearlos.

    Args:
        node: Objeto ``Node`` del driver Python de Neo4j.
        kind: Etiqueta del nodo (``"Norma"`` o ``"UserQuery"``).

    Returns:
        Dict con ``id``, ``label``, ``color``, ``kind`` y ``attrs``.
    """
    nd = dict(node)
    # Los nodos Norma tienen campo "id" (BOE-A-YYYY-NNNN);
    # los UserQuery pueden no tener "id" y se identifican por su texto "query".
    node_id: str = nd.get("id") or nd.get("query", "")[:40] or ""
    label: str = (nd.get("titulo") or nd.get("query") or node_id)[:50]
    return {
        "id": node_id,
        "label": label,
        "color": node_color(kind),
        "kind": kind,
        "attrs": nd,
    }


def fetch_graph(scope: Scope, filters: dict[str, Any]) -> dict[str, Any]:
    """Consulta Neo4j y devuelve ``{nodes, edges}`` en formato sigma_bridge.

    Estrategia *edges-first*: en lugar de muestrear N nodos aleatorios y luego
    buscar aristas entre ellos (que casi nunca coincidirían), se consultan las
    aristas directamente y se extraen los nodos de ambos extremos. El resultado
    es siempre un subgrafo conexo — cada nodo visible tiene al menos una arista.

    Para el scope ``"norma"`` se aplican los filtros del panel al nodo origen
    ``a``; el nodo destino ``b`` no se filtra para no partir cadenas de citas.

    Args:
        scope: Subconjunto del grafo a cargar:
            - ``"norma"`` – solo relaciones Norma→Norma (CITA/DEROGA/MODIFICA).
            - ``"userquery"`` – solo consultas de usuario y sus normas resultado.
            - ``"all"`` – ambos tipos.
        filters: Filtros activos del panel. No debe incluir la clave ``"scope"``.

    Returns:
        Dict ``{"nodes": [...], "edges": [...]}`` listo para ``initSigma()``.
    """
    driver = _get_driver()
    # Usamos dict keyed by id para deduplicar nodos que aparecen en múltiples aristas.
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    try:
        with driver.session(database=settings.neo4j.database) as session:
            if scope in ("norma", "all"):
                where_str, params = build_where("a", filters)
                q = (
                    f"MATCH (a:Norma)-[r]->(b:Norma) {where_str} "
                    f"RETURN a, b, type(r) AS rel_type LIMIT {_MAX_EDGES}"
                )
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
                            "attrs": {},
                        }
                    )

            if scope in ("userquery", "all"):
                # RESULT_EDGE no tiene filtros de usuario aplicables (los campos
                # rango/vigente/fecha son de Norma, no de UserQuery).
                q = (
                    "MATCH (u:UserQuery)-[r:RESULT_EDGE]->(n:Norma) "
                    f"RETURN u, n LIMIT {_MAX_EDGES}"
                )
                for record in session.run(q):
                    u_dict = _node_dict(record["u"], "UserQuery")
                    n_dict = _node_dict(record["n"], "Norma")
                    nodes[u_dict["id"]] = u_dict
                    nodes[n_dict["id"]] = n_dict
                    edges.append(
                        {
                            "src": u_dict["id"],
                            "dst": n_dict["id"],
                            "type": "RESULT_EDGE",
                            "color": EDGE_COLOR,
                            "attrs": {},
                        }
                    )
    except Exception as exc:  # noqa: BLE001
        log.warning("graph_query_failed", scope=scope, error=str(exc))

    return {"nodes": list(nodes.values()), "edges": edges}


@functools.lru_cache(maxsize=32)
def distinct_values(field: str) -> list[str]:
    """Devuelve los valores distintos de una propiedad de Norma, cacheados.

    El resultado se cachea en memoria con ``lru_cache`` para evitar una
    round-trip a Neo4j en cada render del panel de filtros. El cache se
    invalida solo al reiniciar el servidor.

    Args:
        field: Nombre de la propiedad. Debe pertenecer a ``_ALLOWED_FILTER_FIELDS``
            para evitar inyección Cypher (el nombre de campo no puede
            parametrizarse en Cypher y se interpola directamente en la query).

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
