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
    referencias_anteriores no se escribe como propiedad de nodo: se materializan
    como aristas Neo4j.

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
        description="Identificador del boletín oficial (e.g. BOE-A-2015-10565)",
        examples=["BOE-A-2015-10565"],
    )
    fecha_actualizacion: str | None = Field(
        None,
        description="Fecha de última actualización ISO-8601",
        examples=["20251201T120000Z"],
        json_schema_extra={"x_flags": ["metadatos.fecha_actualizacion"]},
    )
    ambito_codigo: int | None = Field(
        None,
        description="Código del ámbito territorial (1=Estatal, 2=Autonómico…)",
        examples=[1],
        json_schema_extra={"x_flags": ["metadatos.ambito"]},
    )
    ambito: str | None = Field(
        None,
        description="Texto del ámbito territorial (e.g. Estatal)",
        examples=["Estatal"],
        json_schema_extra={"x_flags": ["metadatos.ambito"]},
    )
    departamento_codigo: int | None = Field(
        None,
        description="Código del departamento emisor",
        examples=[3681],
        json_schema_extra={"x_flags": ["metadatos.departamento"]},
    )
    departamento: str | None = Field(
        None,
        description="Nombre del departamento emisor",
        examples=["Jefatura del Estado"],
        json_schema_extra={"x_flags": ["metadatos.departamento"]},
    )
    rango_codigo: int | None = Field(
        None,
        description="Código del rango normativo",
        examples=[1300],
        json_schema_extra={"x_flags": ["metadatos.rango"]},
    )
    rango: str | None = Field(
        None,
        description="Texto del rango (e.g. Ley, Real Decreto)",
        examples=["Ley"],
        json_schema_extra={"x_flags": ["metadatos.rango"]},
    )
    fecha_disposicion: str | None = Field(
        None,
        description="Fecha de disposición YYYY-MM-DD",
        examples=["2015-10-01"],
        json_schema_extra={"x_flags": ["metadatos.fecha_disposicion"]},
    )
    numero_oficial: str | None = Field(
        None,
        description="Número oficial de la norma",
        examples=["39/2015"],
        json_schema_extra={"x_flags": ["metadatos.numero_oficial"]},
    )
    titulo: str | None = Field(
        None,
        description="Título oficial de la norma",
        examples=["Ley 39/2015, de 1 de octubre, del Procedimiento Administrativo Común"],
        json_schema_extra={"x_flags": ["metadatos.titulo"]},
    )
    diario: str | None = Field(
        None,
        description="Nombre del boletín oficial",
        examples=["Boletín Oficial del Estado"],
        json_schema_extra={"x_flags": ["metadatos.diario"]},
    )
    fecha_publicacion: str | None = Field(
        None,
        description="Fecha de publicación en el boletín YYYY-MM-DD",
        examples=["2015-10-02"],
        json_schema_extra={"x_flags": ["metadatos.fecha_publicacion"]},
    )
    diario_numero: int | None = Field(
        None,
        description="Número del boletín oficial",
        examples=[236],
        json_schema_extra={"x_flags": ["metadatos.diario_numero"]},
    )
    fecha_vigencia: str | None = Field(
        None,
        description="Fecha de entrada en vigor YYYY-MM-DD",
        examples=["2015-10-02"],
        json_schema_extra={"x_flags": ["metadatos.fecha_vigencia"]},
    )
    estatus_derogacion: str | None = Field(
        None,
        description="S/N — norma derogada",
        examples=["N"],
        json_schema_extra={"x_flags": ["metadatos.estatus_derogacion"]},
    )
    fecha_derogacion: str | None = Field(
        None,
        description="Fecha de derogación YYYY-MM-DD",
        examples=["2022-05-18"],
        json_schema_extra={"x_flags": ["metadatos.fecha_derogacion"]},
    )
    estatus_anulacion: str | None = Field(
        None,
        description="S/N — norma judicialmente anulada",
        examples=["N"],
        json_schema_extra={"x_flags": ["metadatos.estatus_anulacion"]},
    )
    fecha_anulacion: str | None = Field(
        None,
        description="Fecha de anulación YYYY-MM-DD",
        examples=["2022-05-18"],
        json_schema_extra={"x_flags": ["metadatos.fecha_anulacion"]},
    )
    vigencia_agotada: str | None = Field(
        None,
        description="S/N — vigencia agotada por cumplimiento de plazo",
        examples=["N"],
        json_schema_extra={"x_flags": ["metadatos.vigencia_agotada"]},
    )
    vigente: bool | None = Field(
        None,
        description="Calculado: true si estatus_derogacion=N AND estatus_anulacion=N AND vigencia_agotada=N",
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
        description="Código del estado de consolidación",
        examples=[3],
        json_schema_extra={"x_flags": ["metadatos.estado_consolidacion"]},
    )
    estado_consolidacion: str | None = Field(
        None,
        description="Texto del estado de consolidación",
        examples=["Finalizado"],
        json_schema_extra={"x_flags": ["metadatos.estado_consolidacion"]},
    )
    url_eli: str | None = Field(
        None,
        description="URL ELI de la norma",
        examples=["https://www.boe.es/eli/es/l/2015/10/01/39"],
        json_schema_extra={"x_flags": ["metadatos.url_eli"]},
    )
    url_html_consolidada: str | None = Field(
        None,
        description="URL HTML de la versión consolidada",
        examples=["https://www.boe.es/buscar/act.php?id=BOE-A-2015-10565"],
        json_schema_extra={"x_flags": ["metadatos.url_html_consolidada"]},
    )
    materias_codigos: list[int] | None = Field(
        None,
        description="Códigos de materias temáticas",
        examples=[[1270, 1680]],
        json_schema_extra={"x_flags": ["analisis.materias"]},
    )
    materias: list[str] | None = Field(
        None,
        description="Textos de materias temáticas",
        examples=[["Administración Pública"]],
        json_schema_extra={"x_flags": ["analisis.materias"]},
    )
    nota: str | None = Field(
        None,
        description="Notas que aportan información adicional a la norma",
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
    out_dir = base_dir if base_dir is not None else settings.preprocess.ontology_dir
    sem = out_dir / settings.preprocess.semantic_subdir

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

    log.info(
        "\nEsquemas creados",
        semantic_dir=str(sem),
        relaciones=len(settings.relacion.codigos_a_relacion),
    )
