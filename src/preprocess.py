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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog
from lxml import etree
from neo4j import GraphDatabase
from pydantic import BaseModel, Field
from tqdm import tqdm

from src.config import (
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


@dataclass
class ResumenReintento:
    """Resultado de reintentar los errores pendientes.

    Attributes:
        recuperados: ficheros que se procesaron con éxito en el reintento.
        total_intentados: total de errores encontrados en errors/.
    """
    recuperados: int = 0
    total_intentados: int = 0


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
    relacion: str = Field(description="Texto que define la relación (e.g. DEROGA)")
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
    if f.fecha_actualizacion:
        norma.fecha_actualizacion = meta.findtext("fecha_actualizacion")
    if f.ambito:
        amb = meta.find("ambito")
        if amb is not None:
            norma.ambito_codigo = _int_attr(amb, "codigo")
            norma.ambito = amb.text
    if f.titulo:
        norma.titulo = meta.findtext("titulo")
    if f.diario:
        norma.diario = meta.findtext("diario")
    if f.diario_numero:
        raw = meta.findtext("diario_numero")
        norma.diario_numero = int(raw) if raw else None
    if f.departamento:
        dep = meta.find("departamento")
        if dep is not None:
            norma.departamento_codigo = _int_attr(dep, "codigo")
            norma.departamento = dep.text
    if f.rango:
        rng = meta.find("rango")
        if rng is not None:
            norma.rango_codigo = _int_attr(rng, "codigo")
            norma.rango = rng.text
    if f.fecha_disposicion:
        norma.fecha_disposicion = _parse_date(meta.findtext("fecha_disposicion"))
    if f.numero_oficial:
        norma.numero_oficial = meta.findtext("numero_oficial")
    if f.fecha_publicacion:
        norma.fecha_publicacion = _parse_date(meta.findtext("fecha_publicacion"))
    if f.fecha_vigencia:
        norma.fecha_vigencia = _parse_date(meta.findtext("fecha_vigencia"))
    if f.estatus_derogacion:
        norma.estatus_derogacion = meta.findtext("estatus_derogacion")
    if f.fecha_derogacion:
        norma.fecha_derogacion = _parse_date(meta.findtext("fecha_derogacion"))
    if f.estatus_anulacion:
        norma.estatus_anulacion = meta.findtext("estatus_anulacion")
    if f.fecha_anulacion:
        norma.fecha_anulacion = _parse_date(meta.findtext("fecha_anulacion"))
    if f.vigencia_agotada:
        norma.vigencia_agotada = meta.findtext("vigencia_agotada")
    if f.estatus_derogacion and f.estatus_anulacion and f.vigencia_agotada:
        norma.vigente = (
            (norma.estatus_derogacion or "N") == "N"
            and (norma.estatus_anulacion or "N") == "N"
            and (norma.vigencia_agotada or "N") == "N"
        )
    if f.estado_consolidacion:
        ec = meta.find("estado_consolidacion")
        if ec is not None:
            norma.estado_consolidacion_codigo = _int_attr(ec, "codigo")
            norma.estado_consolidacion = ec.text
    if f.url_eli:
        norma.url_eli = meta.findtext("url_eli")
    if f.url_html_consolidada:
        norma.url_html_consolidada = meta.findtext("url_html_consolidada")


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
            norma.materias = [
                m.text or "" for m in materias_el.findall("materia")
            ]
    if f.notas:
        notas_el = analisis_el.find("notas")
        if notas_el is not None:
            norma.nota = " ".join(
                n.text or "" for n in notas_el.findall("nota")
            ).strip() or None
    if f.referencias_anteriores:
        anteriores = analisis_el.find("referencias/anteriores")
        if anteriores is not None:
            for ant in anteriores.findall("anterior"):
                rel_el = ant.find("relacion")
                norma.referencias_anteriores.append(
                    Referencia(
                        id_norma=ant.findtext("id_norma", ""),
                        relacion_codigo=_int_attr(rel_el, "codigo") or 0,
                        relacion=rel_el.text or "" if rel_el is not None else "",
                        texto=ant.findtext("texto", ""),
                    )
                )


# --------------------------------------------------------------------------- #
# Generación de esquemas semánticos                                           #
# --------------------------------------------------------------------------- #

_NORMA_MD_FIELDS: list[tuple[str, str, str, str, str, str]] = [
    ("fecha_actualizacion", "fecha_actualizacion", "string", "no", "Fecha de última actualización ISO-8601", "`20251201T120000Z`"),
    ("ambito", "ambito_codigo", "int", "no", "Código del ámbito territorial", "`1`"),
    ("ambito", "ambito", "string", "no", "Texto del ámbito territorial", "`Estatal`"),
    ("titulo", "titulo", "string", "no", "Título oficial de la norma", "`Ley 39/2015...`"),
    ("diario", "diario", "string", "no", "Nombre del boletín oficial", "`Boletín Oficial del Estado`"),
    ("diario_numero", "diario_numero", "int", "no", "Número del boletín oficial", "`236`"),
    ("departamento", "departamento_codigo", "int", "no", "Código del departamento emisor", "`3681`"),
    ("departamento", "departamento", "string", "no", "Nombre del departamento emisor", "`Jefatura del Estado`"),
    ("rango", "rango_codigo", "int", "no", "Código del rango normativo", "`1300`"),
    ("rango", "rango", "string", "no", "Texto del rango normativo", "`Ley`"),
    ("fecha_disposicion", "fecha_disposicion", "string", "no", "Fecha de disposición (YYYY-MM-DD)", "`2015-10-01`"),
    ("numero_oficial", "numero_oficial", "string", "no", "Número oficial de la norma", "`39/2015`"),
    ("fecha_publicacion", "fecha_publicacion", "string", "no", "Fecha de publicación en BOE (YYYY-MM-DD)", "`2015-10-02`"),
    ("fecha_vigencia", "fecha_vigencia", "string", "no", "Fecha de entrada en vigor (YYYY-MM-DD)", "`2015-10-02`"),
    ("estatus_derogacion", "estatus_derogacion", "string", "no", "S/N — norma derogada", "`N`"),
    ("fecha_derogacion", "fecha_derogacion", "string", "no", "Fecha de derogación (YYYY-MM-DD)", "`2022-05-18`"),
    ("estatus_anulacion", "estatus_anulacion", "string", "no", "S/N — norma judicialmente anulada", "`N`"),
    ("fecha_anulacion", "fecha_anulacion", "string", "no", "Fecha de anulación (YYYY-MM-DD)", "`2022-05-18`"),
    ("vigencia_agotada", "vigencia_agotada", "string", "no", "S/N — vigencia agotada", "`N`"),
    ("estado_consolidacion", "estado_consolidacion_codigo", "int", "no", "Código del estado de consolidación", "`3`"),
    ("estado_consolidacion", "estado_consolidacion", "string", "no", "Texto del estado de consolidación", "`Finalizado`"),
    ("url_eli", "url_eli", "string", "no", "URL ELI de la norma", "`https://...`"),
    ("url_html_consolidada", "url_html_consolidada", "string", "no", "URL HTML de la versión consolidada", "`https://...`"),
]

_ANALISIS_MD_FIELDS: list[tuple[str, str, str, str, str, str]] = [
    ("materias", "materias_codigos", "int[]", "no", "Códigos de materias temáticas", "`[1270, 1680]`"),
    ("materias", "materias", "string[]", "no", "Textos de materias temáticas", '`["Administración Pública"]`'),
    ("notas", "nota", "string", "no", "Nota libre del boletín", "`Publicada en el DOGC...`"),
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

    (humans_nodes / "norma.md").write_text(render_md_norma(settings.parse))
    (agents_nodes / "norma.json").write_text(
        json.dumps(NormaSchema.model_json_schema(), ensure_ascii=False, indent=2)
    )

    for codigo, rel_type in settings.relacion.codigos_a_relacion.items():
        nombre = rel_type.lower()
        (humans_edges / f"{nombre}.md").write_text(render_md_edge(rel_type, codigo))
        (agents_edges / f"{nombre}.json").write_text(
            json.dumps(EdgeSchema.model_json_schema(), ensure_ascii=False, indent=2)
        )

    log.info(
        "\nEsquemas semanticos creados",
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
        all_xmls = [f for d in year_dirs for f in sorted(d.glob("*.xml"))]

        log.info("\nPreprocesando...")
        with self._driver.session(database=self._db) as s:
            with tqdm(all_xmls, unit="norma", dynamic_ncols=True) as bar:
                for xml_path in bar:
                    bar.set_postfix_str(xml_path.stem, refresh=False)
                    self._procesar_fichero(xml_path, s, resumen)

        regenerar_esquemas_semanticos(base_dir=self._ontology_dir)
        log.info(
            "\nPreprocesado completado",
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
            log.warning("Error parseando", path=str(xml_path), error=str(exc))
            self._persistir_error(xml_path, exc)
            resumen.errores += 1
            return

        self._upsert_norma(session, norma)
        resumen.nodos_upsert += 1

        for ref in norma.referencias_anteriores:
            rel_type = settings.relacion.codigos_a_relacion.get(ref.relacion_codigo)
            if rel_type:
                self._upsert_relacion(
                    session,
                    norma.id,
                    rel_type,
                    ref.id_norma,
                    ref.relacion_codigo,
                    ref.texto,
                )
                resumen.aristas_upsert += 1

    def _upsert_norma(self, session: Any, norma: Norma) -> None:
        """Escribe o actualiza un nodo :Norma con MERGE."""
        raw = asdict(norma)
        props = {
            k: v
            for k, v in raw.items()
            if k not in ("id", "referencias_anteriores", "referencias_posteriores")
            and v is not None
        }
        session.run(
            "MERGE (n:Norma {id: $id}) SET n += $props",
            id=norma.id,
            props=props,
        )

    def reintentar(self) -> ResumenReintento:
        """Reintenta todos los XMLs en errors/.

        Para cada error: si parsea con éxito, borra el fichero de error y escribe
        en Neo4j. Si falla de nuevo, incrementa `attempts` en el JSON.

        Returns:
            ResumenReintento con recuperados y total_intentados.
        """
        errors_dir = settings.preprocess.errors_dir
        errors_dir.mkdir(parents=True, exist_ok=True)

        error_files = list(errors_dir.glob("*.json"))
        resumen = ResumenReintento(total_intentados=len(error_files))

        with self._driver.session(database=self._db) as s:
            for error_file in error_files:
                error_data = json.loads(error_file.read_text())
                xml_path = Path(error_data["path"])
                try:
                    norma = parse_xml(xml_path, flags=settings.parse)
                    self._upsert_norma(s, norma)
                    for ref in norma.referencias_anteriores:
                        rel_type = settings.relacion.codigos_a_relacion.get(
                            ref.relacion_codigo
                        )
                        if rel_type:
                            self._upsert_relacion(
                                s,
                                norma.id,
                                rel_type,
                                ref.id_norma,
                                ref.relacion_codigo,
                                ref.texto,
                            )
                    error_file.unlink()
                    resumen.recuperados += 1
                    log.info("Reintento Exitoso", path=str(xml_path))
                except Exception as exc:  # noqa: BLE001
                    error_data["attempts"] = error_data.get("attempts", 1) + 1
                    error_data["error"] = str(exc)
                    error_file.write_text(json.dumps(error_data, ensure_ascii=False))
                    log.warning("Reintento fallido", path=str(xml_path), error=str(exc))

        log.info(
            "\nReintento completado",
            recuperados=resumen.recuperados,
            total=resumen.total_intentados,
        )
        return resumen

    def _persistir_error(self, xml_path: Path, exc: Exception) -> None:
        """Guarda el error de parseo en errors/{stem}.json."""
        errors_dir = settings.preprocess.errors_dir
        errors_dir.mkdir(parents=True, exist_ok=True)
        error_path = errors_dir / f"{xml_path.stem}.json"
        payload = {
            "path": str(xml_path),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(exc),
            "attempts": 1,
        }
        error_path.write_text(json.dumps(payload, ensure_ascii=False))

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
