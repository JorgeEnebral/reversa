"""
Design tokens del grafo de Reversa.

Fuente única de verdad para los colores aplicados a nodos y aristas. Los
tokens se consumen en ``data/graph_repo.py``, que los inyecta en el payload
JSON que viaja al navegador, de modo que ``sigma_bridge.js`` nunca hardcodea
colores: los lee siempre del campo ``color`` que viene de Python.

Este módulo es puro (sin imports de terceros ni I/O) para que pueda
importarse sin efectos secundarios desde cualquier contexto.
"""

from __future__ import annotations

from typing import Final

# Color de relleno por tipo de nodo (kind).
# Norma → verde claro: distingue legislación como el recurso principal del grafo.
# UserQuery → azul: diferencia visualmente las consultas del usuario de las normas.
NODE_COLORS: Final[dict[str, str]] = {
    "Norma": "#86efac",
    "UserQuery": "#2f6fb0",
}

# Color de borde (stroke) por tipo de nodo.
# Más oscuro que el relleno para que los nodos tengan definición en fondos claros.
NODE_BORDER_COLORS: Final[dict[str, str]] = {
    "Norma": "#22c55e",
    "UserQuery": "#1d4e79",
}

# Color para tipos de nodo no contemplados en NODE_COLORS.
DEFAULT_NODE_COLOR: Final[str] = "#94a3b8"

# Color único para todas las aristas. Negro casi puro para máximo contraste
# sobre el fondo blanco/gris suave de la página.
EDGE_COLOR: Final[str] = "#111111"


def node_color(kind: str) -> str:
    """Devuelve el color de relleno para un tipo de nodo.

    Args:
        kind: Etiqueta del nodo (e.g. ``"Norma"``, ``"UserQuery"``).

    Returns:
        Color hexadecimal de relleno. Devuelve ``DEFAULT_NODE_COLOR`` si
        el kind no está registrado en ``NODE_COLORS``.
    """
    return NODE_COLORS.get(kind, DEFAULT_NODE_COLOR)
