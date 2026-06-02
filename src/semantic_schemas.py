"""
Única fuente de verdad de la ontología.

Define nodos, aristas (dataclasses runtime + esquemas Pydantic) y la maquinaria
genérica que, a partir de esos esquemas, genera para cada tipo:

    Esquema Pydantic
        │  .model_json_schema()
        ▼
    JSON formato Anthropic   (agents/*.json)
        │
        ▼
    Markdown para humanos    (humans/*.md)   ← derivado del JSON, no aparte

Los esquemas son la única fuente: contienen todas las variables, su tipo,
descripción, ejemplos y defaults. Añadir o cambiar un campo se hace en un solo
sitio (su `Field`).
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel, ConfigDict, Field

from src.config import ParseFlags, settings

log = structlog.get_logger()


# ─── Modelos runtime (dataclasses) ────────────────────────────────────────── #


@dataclass
class Referencia:
    """Referencia a otra norma extraída de <analisis>/<referencias>/<anteriores>.

    Attributes:
        id_norma: identificador del boletín oficial de la norma referenciada.
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
    """Representación en memoria de una norma parseada del boletín oficial.

    Solo los campos habilitados en ParseFlags tendrán valor; el resto es None.
    referencias_anteriores y referencias_posteriores no se escriben como
    propiedades de nodo: se materializan como aristas Neo4j.

    Attributes:
        id: identificador del boletín oficial (siempre presente, es la clave del nodo).
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
    referencias_posteriores: list[Referencia] = field(default_factory=list)


# ─── Esquemas semánticos: nodos ───────────────────────────────────────────── #


class NormaSchema(BaseModel):
    """Schema del nodo :Norma — todos los campos posibles como Optional.

    `x_flags` por campo declara los flags de ParseFlags que deben estar activos
    para que el campo se documente. `vigente` es derivado: depende de los tres
    flags de estatus.
    """

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "x_name": "Norma",
            "x_description": "Nodo principal del grafo. Una norma consolidada del boletín oficial.",
        },
    )

    id: str = Field(
        description=(
            "Identificador único asignado por el BOE a cada disposición publicada. "
            "Sigue el patrón BOE-[sección]-[año]-[secuencia]: la sección A corresponde "
            "a disposiciones generales (leyes, reales decretos, órdenes ministeriales), "
            "B a disposiciones de las CCAA, C a anuncios de concursos y subastas y D a "
            "anuncios varios. Úsalo para recuperar o enlazar una norma de forma inequívoca."
        ),
        examples=["BOE-A-2015-10565"],
    )

    fecha_actualizacion: str | None = Field(
        None,
        description=(
            "Marca temporal ISO-8601 de la última vez que el sistema del BOE actualizó "
            "los metadatos o el texto consolidado de esta norma. No coincide necesariamente "
            "con ninguna fecha jurídica (publicación, vigor, derogación). Útil para detectar "
            "si hay cambios recientes en la consolidación desde la última ingesta de datos, "
            "o para filtrar normas cuya ficha ha cambiado en un periodo concreto."
        ),
        examples=["20251201T120000Z"],
        json_schema_extra={"x_flags": ["metadatos.fecha_actualizacion"]},
    )

    ambito_codigo: int | None = Field(
        None,
        description=(
            "Código numérico que identifica el ámbito territorial de aplicación de la norma "
            "según el catálogo del BOE. Los valores más frecuentes son: 1 = Estatal, "
            "2 = Autonómico, 3 = Provincial, 4 = Local. Usa este campo (en lugar de `ambito`) "
            "cuando necesites hacer JOIN con otras tablas, agrupar o comparar ámbitos de forma "
            "eficiente en consultas Cypher o SQL."
        ),
        examples=[1],
        json_schema_extra={"x_flags": ["metadatos.ambito"]},
    )

    ambito: str | None = Field(
        None,
        description=(
            "Etiqueta legible del ámbito territorial (p. ej. 'Estatal', 'Autonómico', "
            "'Local'). Derivada del código `ambito_codigo`. Úsala para mostrar al usuario "
            "o para filtrar en lenguaje natural; para filtros programáticos prefiere el código."
        ),
        examples=["Estatal"],
        json_schema_extra={"x_flags": ["metadatos.ambito"]},
    )

    departamento_codigo: int | None = Field(
        None,
        description=(
            "Código numérico del organismo o departamento que emite la disposición, según "
            "el catálogo oficial del BOE (p. ej. 3681 = Jefatura del Estado, 3682 = Presidencia "
            "del Gobierno, 3695 = Ministerio de Hacienda). Permite filtrar todas las normas "
            "dictadas por un ministerio concreto de forma consistente aunque cambie su nombre "
            "entre legislaturas."
        ),
        examples=[3681],
        json_schema_extra={"x_flags": ["metadatos.departamento"]},
    )

    departamento: str | None = Field(
        None,
        description=(
            "Nombre oficial del organismo emisor en el momento de la publicación "
            "(p. ej. 'Jefatura del Estado', 'Ministerio de Transición Ecológica'). "
            "Puede variar entre legislaturas aunque el código permanezca estable. "
            "Útil para presentación; para filtros fiables usa `departamento_codigo`."
        ),
        examples=["Jefatura del Estado"],
        json_schema_extra={"x_flags": ["metadatos.departamento"]},
    )

    rango_codigo: int | None = Field(
        None,
        description=(
            "Código numérico del rango normativo según el catálogo del BOE. Refleja la "
            "jerarquía formal del ordenamiento jurídico español: p. ej. ~1300 = Ley Orgánica, "
            "~1310 = Ley Ordinaria, ~1340 = Real Decreto-ley, ~1350 = Real Decreto, "
            "~1400 = Orden Ministerial. Úsalo para filtrar por nivel jerárquico o para "
            "ordenar normas de mayor a menor rango."
        ),
        examples=[1340],
        json_schema_extra={"x_flags": ["metadatos.rango"]},
    )

    rango: str | None = Field(
        None,
        description=(
            "Denominación textual del rango normativo (p. ej. 'Ley Orgánica', 'Real Decreto', "
            "'Orden ministerial', 'Resolución'). Derivada de `rango_codigo`. Úsala en presentación "
            "o búsquedas en lenguaje natural; para filtros exactos prefiere el código."
        ),
        examples=["Real Decreto"],
        json_schema_extra={"x_flags": ["metadatos.rango"]},
    )

    fecha_disposicion: str | None = Field(
        None,
        description=(
            "Fecha en que el órgano competente firmó o dictó la norma (formato YYYY-MM-DD). "
            "Es la fecha jurídica de creación del acto y la que aparece en el título oficial "
            "(p. ej. 'Ley 39/2015, de 1 de octubre'). Puede diferir de `fecha_publicacion` "
            "en varios días o semanas. Filtra por este campo cuando interese cuándo se adoptó "
            "la decisión normativa, independientemente de cuándo se publicó."
        ),
        examples=["2015-10-01"],
        json_schema_extra={"x_flags": ["metadatos.fecha_disposicion"]},
    )

    numero_oficial: str | None = Field(
        None,
        description=(
            "Número secuencial oficial asignado a la norma dentro de su rango y año, "
            "tal y como aparece en el título (p. ej. '39/2015' para la Ley 39/2015). "
            "En combinación con `rango` y `fecha_disposicion` permite identificar "
            "inequívocamente la norma con la cita jurídica habitual. Útil para búsquedas "
            "cuando el usuario conoce el número pero no el identificador BOE."
        ),
        examples=["39/2015"],
        json_schema_extra={"x_flags": ["metadatos.numero_oficial"]},
    )

    titulo: str | None = Field(
        None,
        description=(
            "Título completo y oficial de la disposición tal y como aparece publicado en el BOE "
            "(p. ej. 'Ley 39/2015, de 1 de octubre, del Procedimiento Administrativo Común de "
            "las Administraciones Públicas'). Es el campo de texto libre más descriptivo de la "
            "norma. Úsalo para búsqueda semántica o fulltext, para mostrar al usuario y para "
            "generar citas bibliográficas jurídicas."
        ),
        examples=["Ley 39/2015, de 1 de octubre, del Procedimiento Administrativo Común"],
        json_schema_extra={"x_flags": ["metadatos.titulo"]},
    )

    diario: str | None = Field(
        None,
        description=(
            "Nombre del boletín oficial en el que se publicó la norma "
            "(p. ej. 'Boletín Oficial del Estado', 'Diari Oficial de la Generalitat de Catalunya'). "
            "La mayoría de normas estatales aparecen en el BOE, pero normas autonómicas o locales "
            "se publican en sus respectivos diarios. Filtra por este campo cuando quieras restringir "
            "la búsqueda a un boletín concreto."
        ),
        examples=["Boletín Oficial del Estado"],
        json_schema_extra={"x_flags": ["metadatos.diario"]},
    )

    fecha_publicacion: str | None = Field(
        None,
        description=(
            "Fecha en que la norma apareció publicada en el boletín oficial (formato YYYY-MM-DD). "
            "Marca el inicio del cómputo de plazos legales para los ciudadanos, salvo que la propia "
            "norma establezca una vacatio legis distinta. Puede coincidir con `fecha_vigencia` (si "
            "entra en vigor el mismo día de publicación) o diferir (p. ej. 20 días de vacatio). "
            "Úsalo para filtrar normas publicadas en un periodo concreto o para ordenar cronológicamente."
        ),
        examples=["2015-10-02"],
        json_schema_extra={"x_flags": ["metadatos.fecha_publicacion"]},
    )

    diario_numero: int | None = Field(
        None,
        description=(
            "Número del ejemplar del boletín oficial en que se publicó la norma "
            "(p. ej. 236 para el BOE núm. 236). Junto con `diario` y `fecha_publicacion`, "
            "permite localizar la edición física o digital exacta del boletín. Útil para "
            "verificar la fuente primaria o para recuperar otras disposiciones publicadas "
            "en el mismo número."
        ),
        examples=[236],
        json_schema_extra={"x_flags": ["metadatos.diario_numero"]},
    )

    fecha_vigencia: str | None = Field(
        None,
        description=(
            "Fecha a partir de la cual la norma produce efectos jurídicos (entrada en vigor), "
            "en formato YYYY-MM-DD. Puede coincidir con `fecha_publicacion` (entrada en vigor "
            "inmediata), ser posterior por vacatio legis (p. ej. 20 días para leyes ordinarias "
            "según el art. 2.1 CC) o, excepcionalmente, ser anterior a la publicación en caso "
            "de retroactividad. Filtra por este campo cuando quieras saber qué normas estaban "
            "en vigor en una fecha determinada."
        ),
        examples=["2015-10-02"],
        json_schema_extra={"x_flags": ["metadatos.fecha_vigencia"]},
    )

    estatus_derogacion: str | None = Field(
        None,
        description=(
            "Indicador 'S'/'N' que señala si la norma ha sido derogada expresa o tácitamente "
            "por una disposición posterior. 'S' = derogada (total o parcialmente), "
            "'N' = no derogada. Una norma derogada deja de aplicarse desde `fecha_derogacion`. "
            "Combínalo con `estatus_anulacion` y `vigencia_agotada` — o directamente con el "
            "campo derivado `vigente` — para determinar si la norma está en vigor."
        ),
        examples=["N"],
        json_schema_extra={"x_flags": ["metadatos.estatus_derogacion"]},
    )

    fecha_derogacion: str | None = Field(
        None,
        description=(
            "Fecha en que la norma fue derogada (formato YYYY-MM-DD). Solo tiene valor cuando "
            "`estatus_derogacion = 'S'`. Permite determinar el periodo de vigencia efectiva de "
            "la norma (entre `fecha_vigencia` y `fecha_derogacion`) y consultar qué régimen "
            "jurídico aplicaba en una fecha histórica concreta."
        ),
        examples=["2022-05-18"],
        json_schema_extra={"x_flags": ["metadatos.fecha_derogacion"]},
    )

    estatus_anulacion: str | None = Field(
        None,
        description=(
            "Indicador 'S'/'N' que señala si la norma ha sido declarada nula por resolución "
            "judicial firme (habitualmente del Tribunal Constitucional o del Tribunal Supremo). "
            "'S' = anulada judicialmente, 'N' = no anulada. La anulación tiene efectos ex tunc "
            "(retroactivos) a diferencia de la derogación. Combínalo con `estatus_derogacion` y "
            "`vigencia_agotada` para calcular `vigente`."
        ),
        examples=["N"],
        json_schema_extra={"x_flags": ["metadatos.estatus_anulacion"]},
    )

    fecha_anulacion: str | None = Field(
        None,
        description=(
            "Fecha de la resolución judicial que declaró la nulidad de la norma "
            "(formato YYYY-MM-DD). Solo tiene valor cuando `estatus_anulacion = 'S'`. "
            "Permite identificar a partir de qué momento la norma quedó sin efecto por "
            "decisión judicial, y distinguirla de la derogación legislativa."
        ),
        examples=["2022-05-18"],
        json_schema_extra={"x_flags": ["metadatos.estatus_anulacion"]},
    )

    vigencia_agotada: str | None = Field(
        None,
        description=(
            "Indicador 'S'/'N' que señala si la norma ha perdido vigencia por el transcurso "
            "del plazo para el que fue dictada, sin necesidad de derogación expresa ni anulación "
            "judicial. Típico en decretos de convocatoria, normas de emergencia con plazo fijo "
            "o disposiciones transitorias. 'S' = vigencia agotada, 'N' = no agotada. "
            "Combínalo con los otros dos estatus o usa directamente `vigente`."
        ),
        examples=["N"],
        json_schema_extra={"x_flags": ["metadatos.vigencia_agotada"]},
    )

    vigente: bool | None = Field(
        None,
        description=(
            "Campo derivado. Vale `true` únicamente cuando los tres indicadores de cese son "
            "negativos: estatus_derogacion = 'N' AND estatus_anulacion = 'N' AND "
            "vigencia_agotada = 'N'. Vale `false` si cualquiera de ellos es 'S'. "
            "Es el filtro principal para restringir búsquedas a normativa actualmente aplicable; "
            "usa `vigente = true` como condición base en la gran mayoría de consultas de usuario "
            "salvo que se pida expresamente normativa histórica o derogada."
        ),
        examples=[True],
        json_schema_extra={
            "x_flags": [
                "metadatos.estatus_derogacion",
                "metadatos.estatus_anulacion",
                "metadatos.vigencia_agotada",
            ]
        },
    )

    estado_consolidacion_codigo: int | None = Field(
        None,
        description=(
            "Código numérico del estado de trabajo editorial del texto consolidado según el "
            "catálogo del BOE. Indica el grado de actualización del texto unificado respecto "
            "a las modificaciones publicadas. Úsalo cuando necesites filtrar solo normas cuyo "
            "texto consolidado esté completamente al día."
        ),
        examples=[3],
        json_schema_extra={"x_flags": ["metadatos.estado_consolidacion"]},
    )

    estado_consolidacion: str | None = Field(
        None,
        description=(
            "Estado editorial del texto consolidado de la norma. Siempre se trata de texto "
            "consolidado (integra modificaciones en un único documento), pero puede estar en "
            "dos estados: "
            "'Finalizado' — el equipo técnico del BOE ha integrado todas las modificaciones, "
            "correcciones y derogaciones parciales publicadas hasta la fecha; el texto es "
            "fiable para aplicar directamente. "
            "'Desactualizado' — existe al menos una modificación publicada en el BOE que aún "
            "no ha sido integrada en el texto único por el personal técnico; el texto puede "
            "estar incompleto. "
            "Filtra por 'Finalizado' cuando necesites texto normativo listo para análisis "
            "o aplicación; advierte al usuario cuando el estado sea 'Desactualizado'."
        ),
        examples=["Finalizado"],
        json_schema_extra={"x_flags": ["metadatos.estado_consolidacion"]},
    )

    url_eli: str | None = Field(
        None,
        description=(
            "URL canónica de la norma según el estándar European Legislation Identifier (ELI), "
            "adoptado por España para identificar unívocamente las normas a nivel europeo. "
            "Sigue el patrón https://www.boe.es/eli/{país}/{tipo}/{fecha}/{número}. "
            "Es el identificador más estable e interoperable para citar la norma en contextos "
            "jurídicos formales, intercambio de datos entre administraciones o linked data."
        ),
        examples=["https://www.boe.es/eli/es/l/2015/10/01/39"],
        json_schema_extra={"x_flags": ["metadatos.url_eli"]},
    )

    url_html_consolidada: str | None = Field(
        None,
        description=(
            "URL de acceso al texto consolidado en formato HTML en la sede electrónica del BOE "
            "(https://www.boe.es/buscar/act.php?id={id}). Apunta siempre a la versión más "
            "actualizada disponible, no a una versión histórica concreta. Úsala para enlazar "
            "al usuario directamente al texto legal completo o para obtener el contenido "
            "mediante scraping/fetch cuando se necesite el articulado íntegro."
        ),
        examples=["https://www.boe.es/buscar/act.php?id=BOE-A-2015-10565"],
        json_schema_extra={"x_flags": ["metadatos.url_html_consolidada"]},
    )

    materias_codigos: list[int] | None = Field(
        None,
        description=(
            "Lista de códigos numéricos de las materias temáticas asignadas a la norma por "
            "los documentalistas del BOE, según el tesauro oficial de materias jurídicas "
            "(p. ej. 1270 = Procedimiento administrativo, 1680 = Función pública). "
            "Permite clasificar y agrupar normas por área de derecho. Usa estos códigos para "
            "filtrar por materia de forma precisa y consistente; una norma puede tener "
            "varias materias asignadas."
        ),
        examples=[[1270, 1680]],
        json_schema_extra={"x_flags": ["analisis.materias"]},
    )

    materias: list[str] | None = Field(
        None,
        description=(
            "Denominaciones textuales de las materias temáticas asignadas a la norma, "
            "correspondientes a los códigos de `materias_codigos` (p. ej. "
            "['Procedimiento administrativo', 'Función pública']). Útil para mostrar "
            "las categorías al usuario o para búsquedas por palabras clave temáticas. "
            "Para filtros programáticos prefiere los códigos."
        ),
        examples=[["Administración Pública"]],
        json_schema_extra={"x_flags": ["analisis.materias"]},
    )

    nota: str | None = Field(
        None,
        description=(
            "Texto libre con observaciones editoriales o de contexto añadidas por los "
            "documentalistas del BOE. Puede incluir: publicación paralela en otros boletines "
            "oficiales (p. ej. 'Publicada también en el DOGC núm. 6958'), advertencias sobre "
            "correcciones de errores, aclaraciones sobre el ámbito de aplicación territorial "
            "u otras indicaciones relevantes que no caben en los campos estructurados. "
            "Consúltalo cuando necesites contexto adicional sobre la publicación o el alcance "
            "de la norma."
        ),
        examples=["Publicada también en el DOGC núm. 6958"],
        json_schema_extra={"x_flags": ["analisis.notas"]},
    )


# ─── Esquemas semánticos: aristas ─────────────────────────────────────────── #


class EdgeSchema(BaseModel):
    """Schema de una arista semántica entre nodos :Norma.

    Es paramétrico: las descripciones usan plantillas `{codigo}` / `{relacion}`
    que `render_edge` rellena por cada relación de codigos_a_relacion.
    """

    model_config = ConfigDict(extra="forbid")

    relacion_codigo: int = Field(
        description="Código de relación BOE ({codigo} = {relacion})",
        examples=[210],
    )
    relacion: str = Field(
        description="Texto que define la relación ({relacion})",
        examples=["DEROGA"],
    )
    texto: str = Field(
        description="Descripción libre del alcance de la relación",
        examples=["los arts. 4 a 7 en su totalidad"],
    )


# ─── Esquemas dinámicos: nodos ────────────────────────────────────────────── #


class UserQuerySchema(BaseModel):
    """Schema del nodo :UserQuery — creado por el LLM en runtime."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "x_name": "UserQuery",
            "x_description": "Nodo de consulta de usuario. Creado por el LLM en runtime.",
        },
    )

    id_nodo: str = Field(
        description="Identificador único del nodo (UUID v4)",
        examples=["a1b2c3d4-e5f6-7890-abcd-ef1234567890"],
    )
    user_id: str = Field(
        default="unknown",
        description="Identificador del usuario",
        examples=["unknown"],
    )
    user_prompt: str = Field(
        description="Prompt en lenguaje natural enviado por el usuario",
        examples=["¿Cuántos reales decretos ha emitido el Ministerio de Hacienda?"],
    )
    bbdd_query: list[str] = Field(
        description="Consultas Cypher generadas por el LLM a partir del prompt",
        examples=[
            [
                "MATCH (n:Norma {rango: 'Real Decreto', departamento: 'Ministerio de Hacienda'}) RETURN count(n) AS total"
            ]
        ],
    )
    answer: str = Field(
        description="Respuesta en lenguaje natural devuelta al usuario",
        examples=["El Ministerio de Hacienda ha emitido 312 reales decretos en el grafo."],
    )
    ts: str = Field(
        description="Timestamp ISO-8601 de creación del nodo (datetime() de Neo4j)",
        examples=["2025-06-01T12:00:00Z"],
    )


# ─── Esquemas dinámicos: aristas ──────────────────────────────────────────── #


class ResultEdgeSchema(BaseModel):
    """Schema de la arista dinámica (:UserQuery)-[:RESULT_EDGE]->(:Norma)."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "x_name": "RESULT_EDGE",
            "x_description": "Arista dinámica (:UserQuery)-[:RESULT_EDGE]->(:Norma). Creada por el LLM en runtime.",
        },
    )

    texto: str = Field(
        description="Motivo de la consulta tool_use que generó esta arista",
        examples=["Reales decretos vigentes del Ministerio de Hacienda"],
    )


# ─── Núcleo genérico: model_json_schema() → formato Anthropic ──────────────── #

# Claves de una property que se conservan en el JSON final (whitelist). El resto
# (title, anyOf, x_flags…) se descarta.
_JSON_TO_MD_TYPE: dict[str, str] = {
    "string": "string",
    "integer": "int",
    "boolean": "bool",
    "number": "float",
}


def _collapse_optional(prop: dict[str, Any]) -> dict[str, Any]:
    """Devuelve la rama no-null de un `anyOf [tipo, null]`.

    Args:
        prop: property cruda de model_json_schema().

    Returns:
        La property si ya tiene `type`, o la rama no-null del anyOf.
    """
    if "anyOf" in prop:
        return next(b for b in prop["anyOf"] if b.get("type") != "null")
    return prop


def _clean_prop(raw: dict[str, Any]) -> dict[str, Any]:
    """Limpia una property de model_json_schema() al formato Anthropic.

    Colapsa Optionals, descarta `title` y el `default: null` de los Optionals, y
    conserva con orden fijo: type → items? → description → default? → examples?.

    Args:
        raw: property cruda de model_json_schema().

    Returns:
        Property limpia para el bloque properties del JSON Anthropic.
    """
    branch = _collapse_optional(raw)
    out: dict[str, Any] = {"type": branch["type"]}
    if branch["type"] == "array":
        out["items"] = branch["items"]
    out["description"] = raw["description"]
    if raw.get("default") is not None:
        out["default"] = raw["default"]
    if "examples" in raw:
        out["examples"] = raw["examples"]
    return out


def schema_to_anthropic(
    model: type[BaseModel],
    *,
    name: str | None = None,
    description: str | None = None,
    include: Callable[[str, dict[str, Any]], bool] | None = None,
) -> dict[str, Any]:
    """Convierte un BaseModel al dict en formato Anthropic.

    Args:
        model: esquema fuente.
        name: nombre del tipo. Si None, se lee de `x_name` del esquema.
        description: descripción del tipo. Si None, se lee de `x_description`.
        include: filtro opcional (nombre_campo, property_cruda) -> bool. Norma lo
            usa para descartar campos según ParseFlags; el resto no lo pasa.

    Returns:
        Dict con claves name, description, input_schema, example.
    """
    raw = model.model_json_schema()
    schema_name = name if name is not None else str(raw["x_name"])
    schema_desc = description if description is not None else str(raw["x_description"])
    req_src = set(raw.get("required", []))

    properties: dict[str, Any] = {}
    required: list[str] = []
    for campo, prop in raw["properties"].items():
        if include is not None and not include(campo, prop):
            continue
        properties[campo] = _clean_prop(prop)
        if campo in req_src:
            required.append(campo)

    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "required": required,
    }
    if raw.get("additionalProperties") is False:
        input_schema["additionalProperties"] = False

    example = {
        campo: prop["examples"][0] for campo, prop in properties.items() if "examples" in prop
    }
    return {
        "name": schema_name,
        "description": schema_desc,
        "input_schema": input_schema,
        "example": example,
    }


# ─── Núcleo genérico: JSON Anthropic → Markdown ───────────────────────────── #


def _md_type(prop: dict[str, Any]) -> str:
    """Notación MD del tipo de una property ('string', 'int[]'…).

    Args:
        prop: property en formato Anthropic.

    Returns:
        Tipo en notación Markdown.
    """
    if prop["type"] == "array":
        return _JSON_TO_MD_TYPE[prop["items"]["type"]] + "[]"
    return _JSON_TO_MD_TYPE[prop["type"]]


def _md_example(value: Any) -> str:
    """Formatea un valor de ejemplo para la columna del .md.

    Strings se muestran tal cual; el resto (bool, listas) en notación JSON para
    que `True`→`true` y las listas conserven su forma.

    Args:
        value: valor de ejemplo.

    Returns:
        Representación textual del ejemplo.
    """
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def anthropic_to_md(schema: dict[str, Any]) -> str:
    """Genera la tabla Markdown de un tipo a partir de su dict Anthropic.

    Args:
        schema: dict en formato Anthropic (salida de schema_to_anthropic / render_edge).

    Returns:
        Contenido Markdown del fichero de documentación.
    """
    req = set(schema["input_schema"]["required"])
    lines = [
        f"# :{schema['name']}",
        "",
        schema["description"],
        "",
        "| Atributo | Tipo | Obligatorio | Descripción | Ejemplo |",
        "|---|---|---|---|---|",
    ]
    for campo, prop in schema["input_schema"]["properties"].items():
        oblig = "sí" if campo in req else "no"
        ejemplo = f"`{_md_example(prop['examples'][0])}`" if "examples" in prop else ""
        lines.append(
            f"| {campo} | {_md_type(prop)} | {oblig} | {prop['description']} | {ejemplo} |"
        )
    return "\n".join(lines) + "\n"


# ─── Filtrado de :Norma por flags de parseo ───────────────────────────────── #


def _flag_on(flags: ParseFlags, ruta: str) -> bool:
    """Indica si un flag cualificado (e.g. 'metadatos.ambito') está activo.

    Respeta la cascada: si el bloque entero es False, todos sus campos están off.

    Args:
        flags: configuración de parseo activa.
        ruta: flag cualificado 'bloque.campo'.

    Returns:
        True si el bloque es un submodelo y el campo está a True.
    """
    bloque_name, attr = ruta.split(".")
    bloque = getattr(flags, bloque_name)
    return bool(bloque) and getattr(bloque, attr, False) is True


def _norma_include(flags: ParseFlags) -> Callable[[str, dict[str, Any]], bool]:
    """Construye el filtro de campos de :Norma según los flags activos.

    Args:
        flags: configuración de parseo activa.

    Returns:
        Predicado (nombre_campo, property_cruda) -> bool. Un campo se incluye si
        todos sus `x_flags` están activos (los campos sin x_flags, como id, siempre).
    """

    def keep(_campo: str, prop: dict[str, Any]) -> bool:
        x_flags = prop.get("x_flags", [])
        return all(_flag_on(flags, ruta) for ruta in x_flags)

    return keep


# ─── Render paramétrico de aristas semánticas ─────────────────────────────── #


def render_edge(rel_type: str, codigo: int) -> dict[str, Any]:
    """Genera el JSON Anthropic de una arista semántica tipada.

    Args:
        rel_type: TYPE Cypher de la relación (e.g. DEROGA).
        codigo: código BOE de la relación (e.g. 210).

    Returns:
        Dict en formato Anthropic, con descripciones y ejemplos parametrizados.
    """
    schema = schema_to_anthropic(
        EdgeSchema,
        name=rel_type,
        description=f"Arista de relación entre normas :Norma. Código BOE: {codigo}.",
    )
    props = schema["input_schema"]["properties"]
    props["relacion_codigo"]["examples"] = [codigo]
    props["relacion"]["examples"] = [rel_type]
    for prop in props.values():
        prop["description"] = prop["description"].format(codigo=codigo, relacion=rel_type)
    schema["example"] = {
        "relacion_codigo": codigo,
        "relacion": rel_type,
        "texto": props["texto"]["examples"][0],
    }
    return schema


# ─── Generación de esquemas ───────────────────────────────────────────────── #


def _write_pair(json_dir: Path, md_dir: Path, nombre: str, schema: dict[str, Any]) -> None:
    """Escribe el .json (agents) y el .md derivado (humans) de un esquema.

    Args:
        json_dir: directorio agents/ destino del .json.
        md_dir: directorio humans/ destino del .md.
        nombre: nombre base del fichero (sin extensión).
        schema: dict en formato Anthropic.
    """
    (json_dir / f"{nombre}.json").write_text(json.dumps(schema, ensure_ascii=False, indent=2))
    (md_dir / f"{nombre}.md").write_text(anthropic_to_md(schema))


def generar_esquemas(base_dir: Path | None = None) -> None:
    """Borra y regenera el directorio semantic-layer con todos los esquemas.

    Escribe esquemas semánticos (Norma, aristas BOE) y dinámicos (UserQuery,
    RESULT_EDGE). El directorio dynamic-layer no se toca nunca.
    .md se guardan en humans/, .json en agents/.

    Args:
        base_dir: directorio raíz de la ontología. Por defecto usa
            settings.preprocess.ontology_dir (útil para pasar tmp_path en tests).
    """
    sem = (
        (base_dir / "semantic-layer")
        if base_dir is not None
        else settings.preprocess.semantic_subdir
    )

    if sem.exists():
        shutil.rmtree(sem)

    humans_nodes = sem / "humans" / "nodes"
    humans_edges = sem / "humans" / "edges"
    agents_nodes = sem / "agents" / "nodes"
    agents_edges = sem / "agents" / "edges"
    for d in (humans_nodes, humans_edges, agents_nodes, agents_edges):
        d.mkdir(parents=True)

    # — Semánticos: nodos
    _write_pair(
        agents_nodes,
        humans_nodes,
        "norma",
        schema_to_anthropic(NormaSchema, include=_norma_include(settings.parse)),
    )

    # — Semánticos: aristas
    for codigo, rel_type in settings.relacion.codigos_a_relacion.items():
        _write_pair(
            agents_edges,
            humans_edges,
            rel_type.lower(),
            render_edge(rel_type, codigo),
        )

    # — Dinámicos: nodos y aristas
    _write_pair(
        agents_nodes,
        humans_nodes,
        "user_query",
        schema_to_anthropic(UserQuerySchema),
    )
    _write_pair(
        agents_edges,
        humans_edges,
        "result_edge",
        schema_to_anthropic(ResultEdgeSchema),
    )

    log.info("\nEsquemas creados", semantic_dir=str(sem))
