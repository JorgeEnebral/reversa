"""
Preprocesado de XMLs del BOE y carga directa a Neo4j.

Uso:
    preprocesador = Preprocesador()
    resumen = preprocesador.preprocesar_todo()
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import structlog
from lxml import etree
from neo4j import GraphDatabase
from pydantic import BaseModel, Field

from src.config import (
    APIConfig,
    PreprocessConfig,
    AnalisisFlags,
    MetadatosFlags,
    ParseFlags,
    settings,
)

log = structlog.get_logger()


# --------------------------------------------------------------------------- #
# Modelos de datos                                                             #
# --------------------------------------------------------------------------- #


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
    estado_consolidacion_codigo: int | None = None
    estado_consolidacion: str | None = None
    url_eli: str | None = None
    url_html_consolidada: str | None = None
    materias_codigos: list[int] | None = None
    materias: list[str] | None = None
    nota: str | None = None
    referencias_anteriores: list[Referencia] = field(default_factory=list)
    referencias_posteriores: list[Referencia] | None = field(default_factory=list)


@dataclass
class ResumenPreproc:
    """Resultado de una operación de preprocesado.

    Attributes:
        procesadas: normas iteradas del disco.
        nodos_upsert: nodos escritos/actualizados en Neo4j.
        aristas_upsert: aristas escritas/actualizadas en Neo4j.
        errores: ficheros que fallaron al parsear.
    """
    procesadas: int = 0
    nodos_upsert: int = 0
    aristas_upsert: int = 0
    errores: int = 0


# --------------------------------------------------------------------------- #
# Schemas Pydantic para generación de documentación                           #
# --------------------------------------------------------------------------- #


class NormaSchema(BaseModel):
    """Schema del nodo :Norma — todos los campos posibles como Optional."""
    
    id: str = Field(description="Identificador BOE (e.g. BOE-A-2015-10565)")
    fecha_actualizacion: str | None = Field(
        None, description="Fecha de última actualización ISO-8601"
    )
    ambito_codigo: int | None = Field(
        None, description="Código del ámbito territorial (1=Estatal, 2=Autonómico…)"
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
    nota: str | None = Field(None, description="Notas que aportan información adicional a la norma")


class EdgeSchema(BaseModel):
    """Schema de una arista entre nodos :Norma."""

    relacion_codigo: int = Field(description="Código de relación BOE (e.g. 210 = DEROGA)")
    relacion: str = Field(description="Texto que define la relación (e.g. DEROGA = 210)")
    texto: str = Field(description="Descripción libre del alcance de la relación")


# --------------------------------------------------------------------------- #
# Helpers de parseo                                                            #
# --------------------------------------------------------------------------- #


def _parse_date(raw: str | None) -> str | None:
    """Convierte YYYYMMDD a YYYY-MM-DD. Devuelve None si la entrada es vacía."""
    if not raw or len(raw) < 8:
        return None
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"


def _int_attr(el: Any, attr: str) -> int | None:
    """Lee un atributo de un elemento XML como int. Devuelve None si falta."""
    val = el.get(attr) if el is not None else None
    if val is None:
        return None
    try:
        return int(val)
    except ValueError:
        return None


def parse_xml(path: Path, flags: ParseFlags) -> Norma:
    """Parsea un XML de la API BOE y devuelve un objeto Norma.

    El id (identificador) se extrae siempre independientemente de los flags,
    ya que es la clave primaria del nodo Neo4j.

    Args:
        path: ruta al fichero XML.
        flags: qué bloques y atributos se extraen.

    Returns:
        Norma con los campos habilitados por flags.

    Raises:
        lxml.etree.XMLSyntaxError: si el XML no es válido.
        ValueError: si no se encuentra el elemento <identificador>.
    """
    tree = etree.parse(path)  # noqa: S320 — ficheros locales de confianza
    root = tree.getroot()
    data = root.find("data")
    if data is None:
        raise ValueError(f"No se encontró <data> en {path}")
    meta = data.find("metadatos")
    if meta is None:
        raise ValueError(f"No se encontró <metadatos> en {path}")

    norma_id = meta.findtext("identificador", "")
    if not norma_id:
        raise ValueError(f"<identificador> vacío en {path}")

    norma = Norma(id=norma_id)
    _parse_metadatos(meta, norma, flags)
    analisis_el = data.find("analisis")
    _parse_analisis(analisis_el, norma, flags)
    return norma


def _parse_metadatos(meta: Any, norma: Norma, flags: ParseFlags) -> None:
    """Rellena los campos de metadatos según los flags activos."""
    if not isinstance(flags.metadatos, MetadatosFlags):
        return

    f = flags.metadatos
    if f.titulo:
        norma.titulo = meta.findtext("titulo")
    if f.diario:
        norma.diario = meta.findtext("diario")
    if f.departamento:
        dep = meta.find("departamento")
        if dep is not None:
            norma.departamento_codigo = _int_attr(dep, "codigo")
            norma.departamento_texto = dep.text
    if f.rango:
        rng = meta.find("rango")
        if rng is not None:
            norma.rango_codigo = _int_attr(rng, "codigo")
            norma.rango_texto = rng.text
    if f.fecha_disposicion:
        norma.fecha_disposicion = _parse_date(
            meta.findtext("fecha_disposicion")
        )
    if f.fecha_publicacion:
        norma.fecha_publicacion = _parse_date(
            meta.findtext("fecha_publicacion")
        )
    if f.fecha_vigencia:
        norma.fecha_vigencia = _parse_date(meta.findtext("fecha_vigencia"))
    if f.fecha_derogacion:
        norma.fecha_derogacion = _parse_date(meta.findtext("fecha_derogacion"))
    if f.numero_oficial:
        norma.numero_oficial = meta.findtext("numero_oficial")
    if f.estatus_derogacion and f.estatus_anulacion and f.vigencia_agotada:
        derogacion = meta.findtext("estatus_derogacion", "N")
        anulacion = meta.findtext("estatus_anulacion", "N")
        agotada = meta.findtext("vigencia_agotada", "N")
        norma.vigente = (
            derogacion == "N" and anulacion == "N" and agotada == "N"
        )
    if f.estado_consolidacion:
        ec = meta.find("estado_consolidacion")
        if ec is not None:
            norma.estado_consolidacion_codigo = _int_attr(ec, "codigo")
            norma.estado_consolidacion_texto = ec.text
    if f.judicialmente_anulada:
        val = meta.findtext("judicialmente_anulada")
        norma.judicialmente_anulada = val == "S" if val else False
    if f.url_eli:
        norma.url_eli = meta.findtext("url_eli")
    if f.url_epub:
        norma.url_epub = meta.findtext("url_epub")
    if f.url_pdf:
        norma.url_pdf = meta.findtext("url_pdf")


def _parse_analisis(analisis_el: Any, norma: Norma, flags: ParseFlags) -> None:
    """Rellena los campos de análisis según los flags activos."""
    if not isinstance(flags.analisis, AnalisisFlags) or analisis_el is None:
        return

    f = flags.analisis
    if f.materias:
        materias_el = analisis_el.find("materias")
        if materias_el is not None:
            norma.materias_codigos = [
                int(m.get("codigo", "0"))
                for m in materias_el.findall("materia")
            ]
            norma.materias_textos = [
                m.text or "" for m in materias_el.findall("materia")
            ]

    if f.referencias_anteriores:
        anteriores = analisis_el.find("referencias/anteriores")
        if anteriores is not None:
            for ant in anteriores.findall("anterior"):
                rel_el = ant.find("relacion")
                norma.referencias_anteriores.append(
                    Referencia(
                        id_norma=ant.findtext("id_norma", ""),
                        codigo=_int_attr(rel_el, "codigo") or 0,
                        texto=ant.findtext("texto", ""),
                    )
                )


# --------------------------------------------------------------------------- #
# Generación de esquemas semánticos                                           #
# --------------------------------------------------------------------------- #

# Metadatos de cada campo de Norma para el .md
# (flag_attr, campo_md, tipo, obligatorio, descripcion, ejemplo)
_NORMA_MD_FIELDS: list[tuple[str, str, str, str, str, str]] = [
    (
        "identificador",
        "id",
        "string",
        "sí",
        "Identificador BOE",
        "`BOE-A-2015-10565`",
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
        "departamento",
        "departamento_codigo",
        "int",
        "no",
        "Código del departamento emisor",
        "`4435`",
    ),
    (
        "departamento",
        "departamento_texto",
        "string",
        "no",
        "Nombre del departamento emisor",
        "`Min. de Trabajo`",
    ),
    (
        "rango",
        "rango_codigo",
        "int",
        "no",
        "Código del rango normativo",
        "`1300`",
    ),
    (
        "rango",
        "rango_texto",
        "string",
        "no",
        "Texto del rango normativo",
        "`Ley`",
    ),
    (
        "fecha_disposicion",
        "fecha_disposicion",
        "string",
        "no",
        "Fecha de disposición (YYYY-MM-DD)",
        "`2015-10-01`",
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
        "fecha_derogacion",
        "fecha_derogacion",
        "string",
        "no",
        "Fecha de derogación (YYYY-MM-DD)",
        "`2022-05-18`",
    ),
    (
        "numero_oficial",
        "numero_oficial",
        "string",
        "no",
        "Número oficial de la norma",
        "`39/2015`",
    ),
    # vigente: se incluye si los 3 estatus están activos
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
        "estado_consolidacion_texto",
        "string",
        "no",
        "Texto del estado de consolidación",
        "`Finalizado`",
    ),
    (
        "judicialmente_anulada",
        "judicialmente_anulada",
        "bool",
        "no",
        "Anulada judicialmente",
        "`false`",
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
        "url_epub",
        "url_epub",
        "string",
        "no",
        "URL EPUB de la norma",
        "`https://...`",
    ),
    (
        "url_pdf",
        "url_pdf",
        "string",
        "no",
        "URL PDF de la norma",
        "`https://...`",
    ),
]

_ANALISIS_MD_FIELDS: list[tuple[str, str, str, str, str, str]] = [
    (
        "materias",
        "materias_codigos",
        "int[]",
        "no",
        "Códigos de materias temáticas",
        "`[663, 821]`",
    ),
    (
        "materias",
        "materias_textos",
        "string[]",
        "no",
        "Textos de materias temáticas",
        '`["Formación..."]`',
    ),
]


def render_md_norma(flags: ParseFlags) -> str:
    """Genera el Markdown de documentación del nodo :Norma según flags activos.

    Args:
        flags: configuración de parseo activa.

    Returns:
        Contenido Markdown del fichero node.norma.md.
    """
    lines = [
        "# :Norma",
        "",
        "Nodo principal del grafo. Una norma consolidada del BOE.",
        "",
        "| Atributo | Tipo | Obligatorio | Descripción | Ejemplo |",
        "|---|---|---|---|---|",
        "| id | string | sí | Identificador BOE | `BOE-A-2015-10565` |",
    ]

    if isinstance(flags.metadatos, MetadatosFlags):
        m = flags.metadatos
        # vigente: campo derivado — se incluye si los 3 estatus están habilitados
        if m.estatus_derogacion and m.estatus_anulacion and m.vigencia_agotada:
            lines.append(
                "| vigente | bool | no | "
                "Calculado: derogacion=N AND anulacion=N AND vigencia_agotada=N | `true` |"
            )
        for flag_attr, campo, tipo, oblig, desc, ejemplo in _NORMA_MD_FIELDS:
            if getattr(m, flag_attr, False):
                lines.append(
                    f"| {campo} | {tipo} | {oblig} | {desc} | {ejemplo} |"
                )

    if isinstance(flags.analisis, AnalisisFlags):
        a = flags.analisis
        for flag_attr, campo, tipo, oblig, desc, ejemplo in _ANALISIS_MD_FIELDS:
            if getattr(a, flag_attr, False):
                lines.append(
                    f"| {campo} | {tipo} | {oblig} | {desc} | {ejemplo} |"
                )

    return "\n".join(lines) + "\n"


def render_md_edge(rel_type: str, codigo: int) -> str:
    """Genera el Markdown de documentación de una arista tipada.

    Args:
        rel_type: TYPE Cypher de la relación (e.g. DEROGA).
        codigo: código BOE de la relación (e.g. 210).

    Returns:
        Contenido Markdown del fichero {rel_type.lower()}.md.
    """
    return (
        f"# :{rel_type}\n"
        "\n"
        f"Arista de relación entre normas. Código BOE: {codigo}.\n"
        "\n"
        "| Atributo | Tipo | Obligatorio | Descripción | Ejemplo |\n"
        "|---|---|---|---|---|\n"
        f"| codigo | int | sí | Código de relación BOE | `{codigo}` |\n"
        "| texto | string | sí | Descripción libre del alcance | `los arts. 4 a 7...` |\n"
    )


def regenerar_esquemas_semanticos(base_dir: Path | None = None) -> None:
    """Borra y regenera el directorio semantic-layer a partir de los flags activos.

    El directorio dynamic-layer no se toca nunca.

    Args:
        base_dir: directorio raíz de la ontología. Por defecto usa
            settings.ontology.output_dir (útil para pasar tmp_path en tests).
    """
    out_dir = base_dir if base_dir is not None else settings.ontology.output_dir
    sem = out_dir / settings.ontology.semantic_subdir

    if sem.exists():
        shutil.rmtree(sem)
    (sem / "nodes").mkdir(parents=True)
    (sem / "edges").mkdir(parents=True)

    (sem / "nodes" / "node.norma.md").write_text(
        render_md_norma(settings.parse)
    )
    (sem / "nodes" / "node.norma.schema.json").write_text(
        json.dumps(
            NormaSchema.model_json_schema(), ensure_ascii=False, indent=2
        )
    )

    for codigo, rel_type in settings.relacion.codigos_a_relacion.items():
        nombre = rel_type.lower()
        (sem / "edges" / f"{nombre}.md").write_text(
            render_md_edge(rel_type, codigo)
        )
        (sem / "edges" / f"{nombre}.schema.json").write_text(
            json.dumps(
                EdgeSchema.model_json_schema(), ensure_ascii=False, indent=2
            )
        )

    log.info(
        "esquemas_semanticos_regenerados",
        semantic_dir=str(sem),
        relaciones=len(settings.relacion.codigos_a_relacion),
    )


# --------------------------------------------------------------------------- #
# Preprocesador                                                                #
# --------------------------------------------------------------------------- #


class Preprocesador:
    """Parsea XMLs del BOE y escribe nodos/aristas directamente en Neo4j.

    Usa MERGE para garantizar idempotencia: relanzar el preprocesado sobre los
    mismos ficheros no duplica nodos ni aristas.

    Args:
        config: configuración de ontología (para regenerar esquemas). Por defecto
            usa settings.ontology.

    Example:
        >>> preprocesador = Preprocesador()
        >>> resumen = preprocesador.preprocesar_todo()
        >>> print(resumen.nodos_upsert, "/", resumen.procesadas)
    """

    def __init__(self) -> None:
        
        self._driver = GraphDatabase.driver(
            settings.neo4j.uri,
            auth=(settings.neo4j.user, settings.neo4j.password),
        )
        self._db = settings.neo4j.database
        
        self._ontology_dir = settings.preprocess.ontology_dir
        self.api_raw_dir = settings.api.raw_dir

    def preprocesar_todo(self) -> ResumenPreproc:
        """Recorre todos los XMLs en data/api/raw y los carga en Neo4j.

        Al finalizar regenera los esquemas semánticos.

        Returns:
            ResumenPreproc con totales de la operación.
        """
        resumen = ResumenPreproc()
        year_dirs = sorted(p for p in self.api_raw_dir.iterdir() if p.is_dir())

        with self._driver.session(database=self._db) as s:
            for year_dir in year_dirs:
                for xml_path in sorted(year_dir.glob("*.xml")):
                    self._procesar_fichero(xml_path, s, resumen)

        regenerar_esquemas_semanticos(base_dir=self._ontology_dir)
        log.info(
            "preprocesado_completado",
            procesadas=resumen.procesadas,
            nodos=resumen.nodos_upsert,
            aristas=resumen.aristas_upsert,
            errores=resumen.errores,
        )
        return resumen

    def _procesar_fichero(
        self, xml_path: Path, session: Any, resumen: ResumenPreproc
    ) -> None:
        """Parsea un fichero y escribe en Neo4j. Actualiza resumen en sitio."""
        resumen.procesadas += 1
        try:
            norma = parse_xml(xml_path, flags=settings.parse)
        except Exception as exc:  # noqa: BLE001
            log.warning("error_parseando", path=str(xml_path), error=str(exc))
            resumen.errores += 1
            return

        self._upsert_norma(session, norma)
        resumen.nodos_upsert += 1

        for ref in norma.referencias_anteriores:
            rel_type = settings.relacion.codigos_a_relacion.get(ref.codigo)
            if rel_type:
                self._upsert_relacion(
                    session,
                    norma.id,
                    rel_type,
                    ref.id_norma,
                    ref.codigo,
                    ref.texto,
                )
                resumen.aristas_upsert += 1

    def _upsert_norma(self, session: Any, norma: Norma) -> None:
        """Escribe o actualiza un nodo :Norma con MERGE."""
        raw = asdict(norma)
        props = {
            k: v
            for k, v in raw.items()
            if k not in ("id", "referencias_anteriores") and v is not None
        }
        session.run(
            "MERGE (n:Norma {id: $id}) SET n += $props",
            id=norma.id,
            props=props,
        )

    def _upsert_relacion(
        self,
        session: Any,
        src_id: str,
        rel_type: str,
        dst_id: str,
        codigo: int,
        texto: str,
    ) -> None:
        """Escribe o actualiza una arista tipada con MERGE.

        rel_type ya está validado como valor en codigos_a_relacion.
        """
        query = (
            f"MERGE (a:Norma {{id: $src}})"
            f" MERGE (b:Norma {{id: $dst}})"
            f" MERGE (a)-[r:{rel_type} {{codigo: $codigo}}]->(b)"
            f" SET r.texto = $texto"
        )
        session.run(query, src=src_id, dst=dst_id, codigo=codigo, texto=texto)
