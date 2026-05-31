"""
Única fuente de verdad de la ontología.

Define nodos, aristas y renderers Markdown/JSON para las capas semántica y dinámica.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pydantic import BaseModel, ConfigDict, Field

from src.config import AnalisisFlags, MetadatosFlags, ParseFlags

# ─── Helper genérico de rendering ─────────────────────────────────────────── #

# (campo, tipo, oblig, desc, ejemplo)
_SchemaField = tuple[str, str, str, str, str]

# (flag_attr, campo, tipo, oblig, desc, ejemplo) — solo para _NORMA_MD_FIELDS
_NormaField = tuple[str, str, str, str, str, str]


def _render_schema_md(
    label: str, description: str, fields: list[_SchemaField]
) -> str:
    """Genera una tabla Markdown de documentación para un tipo Neo4j.

    Args:
        label: etiqueta Neo4j del tipo (e.g. Norma, RESULT_EDGE).
        description: descripción de una línea del tipo.
        fields: lista de (campo, tipo, oblig, desc, ejemplo).

    Returns:
        Contenido Markdown del fichero de documentación.
    """
    lines = [
        f"# :{label}",
        "",
        description,
        "",
        "| Atributo | Tipo | Obligatorio | Descripción | Ejemplo |",
        "|---|---|---|---|---|",
    ]
    for campo, tipo, oblig, desc, ejemplo in fields:
        lines.append(f"| {campo} | {tipo} | {oblig} | {desc} | {ejemplo} |")
    return "\n".join(lines) + "\n"


# ─── Modelos runtime (dataclasses) ────────────────────────────────────────── #


@dataclass
class Referencia:
    """Referencia a otra norma extraída de <analisis>/<referencias>/<anteriores>.

    Attributes:
        id_norma: identificador BOE de la norma referenciada.
        relacion_codigo: código de relación BOE (e.g. 210 = DEROGA).
        relacion: texto que define relación BOE (e.g. DEROGA = 210).
        texto: descripción libre del alcance de la relación.
    """

    id_norma: str
    relacion_codigo: int
    relacion: str
    texto: str


@dataclass
class Norma:
    """Representación en memoria de una norma BOE parseada.

    Solo los campos habilitados en ParseFlags tendrán valor; el resto es None.
    referencias_anteriores no se escribe como propiedad de nodo: se materializan
    como aristas Neo4j.

    Attributes:
        id: identificador BOE (siempre presente, es la clave del nodo).
    """

    id: str
    fecha_actualizacion: str | None = None
    ambito_codigo: int | None = None
    ambito: str | None = None
    departamento_codigo: int | None = None
    departamento: str | None = None
    rango_codigo: int | None = None
    rango: str | None = None
    fecha_disposicion: str | None = None
    numero_oficial: str | None = None
    titulo: str | None = None
    diario: str | None = None
    fecha_publicacion: str | None = None
    diario_numero: int | None = None
    fecha_vigencia: str | None = None
    estatus_derogacion: str | None = None
    fecha_derogacion: str | None = None
    estatus_anulacion: str | None = None
    fecha_anulacion: str | None = None
    vigencia_agotada: str | None = None
    vigente: bool | None = None
    estado_consolidacion_codigo: int | None = None
    estado_consolidacion: str | None = None
    url_eli: str | None = None
    url_html_consolidada: str | None = None
    materias_codigos: list[int] | None = None
    materias: list[str] | None = None
    nota: str | None = None
    referencias_anteriores: list[Referencia] = field(default_factory=list)


# ─── Esquemas semánticos: nodos ───────────────────────────────────────────── #


class NormaSchema(BaseModel):
    """Schema del nodo :Norma — todos los campos posibles como Optional."""

    id: str = Field(description="Identificador BOE (e.g. BOE-A-2015-10565)")
    fecha_actualizacion: str | None = Field(
        None, description="Fecha de última actualización ISO-8601"
    )
    ambito_codigo: int | None = Field(
        None,
        description="Código del ámbito territorial (1=Estatal, 2=Autonómico…)",
    )
    ambito: str | None = Field(
        None, description="Texto del ámbito territorial (e.g. Estatal)"
    )
    departamento_codigo: int | None = Field(
        None, description="Código del departamento emisor"
    )
    departamento: str | None = Field(
        None, description="Nombre del departamento emisor"
    )
    rango_codigo: int | None = Field(
        None, description="Código del rango normativo"
    )
    rango: str | None = Field(
        None, description="Texto del rango (e.g. Ley, Real Decreto)"
    )
    fecha_disposicion: str | None = Field(
        None, description="Fecha de disposición YYYY-MM-DD"
    )
    numero_oficial: str | None = Field(
        None, description="Número oficial de la norma"
    )
    titulo: str | None = Field(None, description="Título oficial de la norma")
    diario: str | None = Field(None, description="Nombre del boletín oficial")
    fecha_publicacion: str | None = Field(
        None, description="Fecha de publicación en el BOE YYYY-MM-DD"
    )
    diario_numero: int | None = Field(
        None, description="Número del boletín oficial"
    )
    fecha_vigencia: str | None = Field(
        None, description="Fecha de entrada en vigor YYYY-MM-DD"
    )
    estatus_derogacion: str | None = Field(
        None, description="S/N — norma derogada"
    )
    fecha_derogacion: str | None = Field(
        None, description="Fecha de derogación YYYY-MM-DD"
    )
    estatus_anulacion: str | None = Field(
        None, description="S/N — norma judicialmente anulada"
    )
    fecha_anulacion: str | None = Field(
        None, description="Fecha de anulación YYYY-MM-DD"
    )
    vigencia_agotada: str | None = Field(
        None, description="S/N — vigencia agotada por cumplimiento de plazo"
    )
    estado_consolidacion_codigo: int | None = Field(
        None, description="Código del estado de consolidación"
    )
    estado_consolidacion: str | None = Field(
        None, description="Texto del estado de consolidación"
    )
    url_eli: str | None = Field(None, description="URL ELI de la norma")
    url_html_consolidada: str | None = Field(
        None, description="URL HTML de la versión consolidada"
    )
    materias_codigos: list[int] | None = Field(
        None, description="Códigos de materias temáticas"
    )
    materias: list[str] | None = Field(
        None, description="Textos de materias temáticas"
    )
    nota: str | None = Field(
        None, description="Notas que aportan información adicional a la norma"
    )


# ─── Esquemas semánticos: aristas ─────────────────────────────────────────── #


class EdgeSchema(BaseModel):
    """Schema de una arista semántica entre nodos :Norma."""

    relacion_codigo: int = Field(
        description="Código de relación BOE (e.g. 210 = DEROGA)"
    )
    relacion: str = Field(
        description="Texto que define la relación (e.g. DEROGA)"
    )
    texto: str = Field(
        description="Descripción libre del alcance de la relación"
    )


# ─── Esquemas dinámicos: nodos ────────────────────────────────────────────── #


class UserQuerySchema(BaseModel):
    """Schema del nodo :UserQuery — creado por el LLM en runtime."""

    model_config = ConfigDict(extra="forbid")

    id_nodo: str = Field(description="Identificador único del nodo (UUID v4)")
    user_id: str = Field(
        default="unknown", description="Identificador del usuario"
    )
    user_prompt: str = Field(
        description="Prompt en lenguaje natural enviado por el usuario"
    )
    bbdd_query: list[str] = Field(
        description="Consultas Cypher generadas por el LLM a partir del prompt"
    )
    answer: str = Field(
        description="Respuesta en lenguaje natural devuelta al usuario"
    )


# ─── Esquemas dinámicos: aristas ──────────────────────────────────────────── #


class ResultEdgeSchema(BaseModel):
    """Schema de la arista dinámica (:UserQuery)-[:RESULT_EDGE]->(:Norma)."""

    model_config = ConfigDict(extra="forbid")

    texto: str = Field(
        description="Texto resumen de qué resuelve la bbdd_query que generó esta arista"
    )


# ─── Tablas de campos para render_md_norma ────────────────────────────────── #

_NORMA_MD_FIELDS: list[_NormaField] = [
    (
        "fecha_actualizacion",
        "fecha_actualizacion",
        "string",
        "no",
        "Fecha de última actualización ISO-8601",
        "`20251201T120000Z`",
    ),
    (
        "ambito",
        "ambito_codigo",
        "int",
        "no",
        "Código del ámbito territorial",
        "`1`",
    ),
    (
        "ambito",
        "ambito",
        "string",
        "no",
        "Texto del ámbito territorial",
        "`Estatal`",
    ),
    (
        "titulo",
        "titulo",
        "string",
        "no",
        "Título oficial de la norma",
        "`Ley 39/2015...`",
    ),
    (
        "diario",
        "diario",
        "string",
        "no",
        "Nombre del boletín oficial",
        "`Boletín Oficial del Estado`",
    ),
    (
        "diario_numero",
        "diario_numero",
        "int",
        "no",
        "Número del boletín oficial",
        "`236`",
    ),
    (
        "departamento",
        "departamento_codigo",
        "int",
        "no",
        "Código del departamento emisor",
        "`3681`",
    ),
    (
        "departamento",
        "departamento",
        "string",
        "no",
        "Nombre del departamento emisor",
        "`Jefatura del Estado`",
    ),
    (
        "rango",
        "rango_codigo",
        "int",
        "no",
        "Código del rango normativo",
        "`1300`",
    ),
    ("rango", "rango", "string", "no", "Texto del rango normativo", "`Ley`"),
    (
        "fecha_disposicion",
        "fecha_disposicion",
        "string",
        "no",
        "Fecha de disposición (YYYY-MM-DD)",
        "`2015-10-01`",
    ),
    (
        "numero_oficial",
        "numero_oficial",
        "string",
        "no",
        "Número oficial de la norma",
        "`39/2015`",
    ),
    (
        "fecha_publicacion",
        "fecha_publicacion",
        "string",
        "no",
        "Fecha de publicación en BOE (YYYY-MM-DD)",
        "`2015-10-02`",
    ),
    (
        "fecha_vigencia",
        "fecha_vigencia",
        "string",
        "no",
        "Fecha de entrada en vigor (YYYY-MM-DD)",
        "`2015-10-02`",
    ),
    (
        "estatus_derogacion",
        "estatus_derogacion",
        "string",
        "no",
        "S/N — norma derogada",
        "`N`",
    ),
    (
        "fecha_derogacion",
        "fecha_derogacion",
        "string",
        "no",
        "Fecha de derogación (YYYY-MM-DD)",
        "`2022-05-18`",
    ),
    (
        "estatus_anulacion",
        "estatus_anulacion",
        "string",
        "no",
        "S/N — norma judicialmente anulada",
        "`N`",
    ),
    (
        "fecha_anulacion",
        "fecha_anulacion",
        "string",
        "no",
        "Fecha de anulación (YYYY-MM-DD)",
        "`2022-05-18`",
    ),
    (
        "vigencia_agotada",
        "vigencia_agotada",
        "string",
        "no",
        "S/N — vigencia agotada",
        "`N`",
    ),
    (
        "estado_consolidacion",
        "estado_consolidacion_codigo",
        "int",
        "no",
        "Código del estado de consolidación",
        "`3`",
    ),
    (
        "estado_consolidacion",
        "estado_consolidacion",
        "string",
        "no",
        "Texto del estado de consolidación",
        "`Finalizado`",
    ),
    (
        "url_eli",
        "url_eli",
        "string",
        "no",
        "URL ELI de la norma",
        "`https://...`",
    ),
    (
        "url_html_consolidada",
        "url_html_consolidada",
        "string",
        "no",
        "URL HTML de la versión consolidada",
        "`https://...`",
    ),
]

_ANALISIS_MD_FIELDS: list[_NormaField] = [
    (
        "materias",
        "materias_codigos",
        "int[]",
        "no",
        "Códigos de materias temáticas",
        "`[1270, 1680]`",
    ),
    (
        "materias",
        "materias",
        "string[]",
        "no",
        "Textos de materias temáticas",
        '`["Administración Pública"]`',
    ),
    (
        "notas",
        "nota",
        "string",
        "no",
        "Nota libre del boletín",
        "`Publicada en el DOGC...`",
    ),
]


# ─── Renderers públicos ───────────────────────────────────────────────────── #


def render_md_norma(flags: ParseFlags) -> str:
    """Genera el Markdown de documentación del nodo :Norma según flags activos.

    Args:
        flags: configuración de parseo activa.

    Returns:
        Contenido Markdown del fichero norma.md.
    """
    fields: list[_SchemaField] = [
        ("id", "string", "sí", "Identificador BOE", "`BOE-A-2015-10565`"),
    ]

    if isinstance(flags.metadatos, MetadatosFlags):
        m = flags.metadatos
        if m.estatus_derogacion and m.estatus_anulacion and m.vigencia_agotada:
            fields.append(
                (
                    "vigente",
                    "bool",
                    "no",
                    "Calculado: derogacion=N AND anulacion=N AND vigencia_agotada=N",
                    "`true`",
                )
            )
        for flag_attr, campo, tipo, oblig, desc, ejemplo in _NORMA_MD_FIELDS:
            if getattr(m, flag_attr, False):
                fields.append((campo, tipo, oblig, desc, ejemplo))

    if isinstance(flags.analisis, AnalisisFlags):
        a = flags.analisis
        for flag_attr, campo, tipo, oblig, desc, ejemplo in _ANALISIS_MD_FIELDS:
            if getattr(a, flag_attr, False):
                fields.append((campo, tipo, oblig, desc, ejemplo))

    return _render_schema_md(
        "Norma",
        "Nodo principal del grafo. Una norma consolidada del BOE.",
        fields,
    )


def render_md_edge(rel_type: str, codigo: int) -> str:
    """Genera el Markdown de documentación de una arista semántica tipada.

    Args:
        rel_type: TYPE Cypher de la relación (e.g. DEROGA).
        codigo: código BOE de la relación (e.g. 210).

    Returns:
        Contenido Markdown del fichero {rel_type.lower()}.md.
    """
    fields: list[_SchemaField] = [
        ("codigo", "int", "sí", "Código de relación BOE", f"`{codigo}`"),
        (
            "texto",
            "string",
            "sí",
            "Descripción libre del alcance",
            "`los arts. 4 a 7...`",
        ),
    ]
    return _render_schema_md(
        rel_type,
        f"Arista de relación entre normas. Código BOE: {codigo}.",
        fields,
    )


def render_md_user_query() -> str:
    """Genera el Markdown de documentación del nodo :UserQuery.

    Returns:
        Contenido Markdown del fichero user_query.md.
    """
    fields: list[_SchemaField] = [
        (
            "id_nodo",
            "string",
            "sí",
            "Identificador único del nodo (UUID v4)",
            "`a1b2-...`",
        ),
        (
            "user_id",
            "string",
            "no",
            'Identificador del usuario. Default: "unknown"',
            "`user-42`",
        ),
        (
            "user_prompt",
            "string",
            "sí",
            "Prompt en lenguaje natural enviado por el usuario",
            "`¿Qué dice la Ley 39/2015?`",
        ),
        (
            "bbdd_query",
            "string[]",
            "sí",
            "Consultas Cypher generadas por el LLM a partir del prompt",
            '`["MATCH (n:Norma)..."]`',
        ),
        (
            "answer",
            "string",
            "sí",
            "Respuesta en lenguaje natural devuelta al usuario",
            "`La ley establece...`",
        ),
    ]
    return _render_schema_md(
        "UserQuery",
        "Nodo de consulta de usuario. Creado por el LLM en runtime.",
        fields,
    )


def render_md_result_edge() -> str:
    """Genera el Markdown de documentación de la arista :RESULT_EDGE.

    Returns:
        Contenido Markdown del fichero result_edge.md.
    """
    fields: list[_SchemaField] = [
        (
            "texto",
            "string",
            "sí",
            "Texto resumen de qué resuelve la bbdd_query que generó esta arista",
            "Las 5 normas más modificadas por otras normas.",
        ),
    ]
    return _render_schema_md(
        "RESULT_EDGE",
        "Arista dinámica (:UserQuery)-[:RESULT_EDGE]->(:Norma). Creada por el LLM en runtime.",
        fields,
    )
