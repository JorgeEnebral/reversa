"""
Preprocesado de XMLs del BOE y carga directa a Neo4j.

Uso:
    preprocesador = Preprocesador()
    resumen = preprocesador.preprocesar_todo()
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import structlog
from lxml import etree
from neo4j import GraphDatabase
from tqdm import tqdm

from src.config import (
    AnalisisFlags,
    MetadatosFlags,
    ParseFlags,
    Settings,
    settings,
)
from src.schemas import (
    EdgeSchema,
    Norma,
    NormaSchema,
    Referencia,
    ResultEdgeSchema,
    UserQuerySchema,
    render_md_edge,
    render_md_norma,
    render_md_result_edge,
    render_md_user_query,
)

log = structlog.get_logger()


# --------------------------------------------------------------------------- #
# Modelos de datos                                                             #
# --------------------------------------------------------------------------- #


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
# Generación de esquemas                                                      #
# --------------------------------------------------------------------------- #


def generar_esquemas(base_dir: Path | None = None) -> None:
    """Borra y regenera el directorio semantic-layer con todos los esquemas.

    Escribe esquemas semánticos (Norma, aristas BOE) y dinámicos (UserQuery,
    RESULT_EDGE). El directorio dynamic-layer no se toca nunca.
    .md se guardan en humans/, .json en agents/.

    Args:
        base_dir: directorio raíz de la ontología. Por defecto usa
            settings.preprocess.ontology_dir (útil para pasar tmp_path en tests).
    """
    out_dir = (
        base_dir if base_dir is not None else settings.preprocess.ontology_dir
    )
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
    (humans_nodes / "norma.md").write_text(render_md_norma(settings.parse))
    (agents_nodes / "norma.json").write_text(
        json.dumps(
            NormaSchema.model_json_schema(), ensure_ascii=False, indent=2
        )
    )

    # — Semánticos: aristas
    for codigo, rel_type in settings.relacion.codigos_a_relacion.items():
        nombre = rel_type.lower()
        (humans_edges / f"{nombre}.md").write_text(
            render_md_edge(rel_type, codigo)
        )
        (agents_edges / f"{nombre}.json").write_text(
            json.dumps(
                EdgeSchema.model_json_schema(), ensure_ascii=False, indent=2
            )
        )

    # — Dinámicos: nodos
    (humans_nodes / "user_query.md").write_text(render_md_user_query())
    (agents_nodes / "user_query.json").write_text(
        json.dumps(
            UserQuerySchema.model_json_schema(), ensure_ascii=False, indent=2
        )
    )

    # — Dinámicos: aristas
    (humans_edges / "result_edge.md").write_text(render_md_result_edge())
    (agents_edges / "result_edge.json").write_text(
        json.dumps(
            ResultEdgeSchema.model_json_schema(), ensure_ascii=False, indent=2
        )
    )

    log.info(
        "\nEsquemas creados",
        semantic_dir=str(sem),
        relaciones=len(settings.relacion.codigos_a_relacion),
    )


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
        norma.fecha_disposicion = _parse_date(
            meta.findtext("fecha_disposicion")
        )
    if f.numero_oficial:
        norma.numero_oficial = meta.findtext("numero_oficial")
    if f.fecha_publicacion:
        norma.fecha_publicacion = _parse_date(
            meta.findtext("fecha_publicacion")
        )
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
            norma.nota = (
                " ".join(n.text or "" for n in notas_el.findall("nota")).strip()
                or None
            )
    if f.referencias_anteriores:
        anteriores = analisis_el.find("referencias/anteriores")
        if anteriores is not None:
            for ant in anteriores.findall("anterior"):
                rel_el = ant.find("relacion")
                norma.referencias_anteriores.append(
                    Referencia(
                        id_norma=ant.findtext("id_norma", ""),
                        relacion_codigo=_int_attr(rel_el, "codigo") or 0,
                        relacion=rel_el.text or ""
                        if rel_el is not None
                        else "",
                        texto=ant.findtext("texto", ""),
                    )
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

    def __init__(self, config: Settings = settings) -> None:
        self._cfg = config
        self._driver = GraphDatabase.driver(
            config.neo4j.uri,
            auth=(config.neo4j.user, config.neo4j.password),
        )
        self._db = config.neo4j.database
        self._ontology_dir = config.preprocess.ontology_dir
        self.api_raw_dir = config.api.raw_dir

    def preprocesar_todo(self) -> ResumenPreproc:
        """Recorre todos los XMLs en ontology/kinetic-layer/api_boe/raw y los carga en Neo4j.

        Al finalizar genera los esquemas.

        Returns:
            ResumenPreproc con totales de la operación.
        """
        resumen = ResumenPreproc()
        year_dirs = sorted(p for p in self.api_raw_dir.iterdir() if p.is_dir())
        all_xmls = [f for d in year_dirs for f in sorted(d.glob("*.xml"))]
        self._limpiar_grafo()
        
        log.info("\nPreprocesando...")
        with self._driver.session(database=self._db) as s:
            with tqdm(all_xmls, unit="norma", dynamic_ncols=True) as bar:
                for xml_path in bar:
                    bar.set_postfix_str(xml_path.stem, refresh=False)
                    self._procesar_fichero(xml_path, s, resumen)

        generar_esquemas(base_dir=self._ontology_dir)
        log.info(
            "\nPreprocesado completado",
            procesadas=resumen.procesadas,
            nodos=resumen.nodos_upsert,
            aristas=resumen.aristas_upsert,
            errores=resumen.errores,
        )
        self.reintentar()
        return resumen

    def _limpiar_grafo(self) -> None:
        """Borra todos los nodos y aristas del grafo antes del procesado masivo."""
        with self._driver.session(database=self._db) as s:
            s.run("MATCH (n) DETACH DELETE n")
        log.info("Grafo limpiado")

    def _procesar_fichero(
        self, xml_path: Path, session: Any, resumen: ResumenPreproc
    ) -> None:
        """Parsea un fichero y escribe en Neo4j. Actualiza resumen en sitio."""
        resumen.procesadas += 1
        try:
            norma = parse_xml(xml_path, flags=self._cfg.parse)
        except Exception as exc:  # noqa: BLE001
            log.warning("Error parseando", path=str(xml_path), error=str(exc))
            self._persistir_error(xml_path, exc)
            resumen.errores += 1
            return

        self._upsert_norma(session, norma)
        resumen.nodos_upsert += 1

        for ref in norma.referencias_anteriores:
            rel_type = self._cfg.relacion.codigos_a_relacion.get(
                ref.relacion_codigo
            )
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
        """Crea una arista tipada por cada referencia del XML.

        Usa MATCH en ambos nodos: si la norma destino no existe en el corpus
        la arista se omite, garantizando que no se crean nodos stub.
        rel_type ya está validado como valor en codigos_a_relacion.
        """
        query = (
            f"MATCH (a:Norma {{id: $src}})"
            f" MERGE (b:Norma {{id: $dst}})"
            f" CREATE (a)-[:{rel_type} {{codigo: $codigo, texto: $texto}}]->(b)"
        )
        session.run(query, src=src_id, dst=dst_id, codigo=codigo, texto=texto)

    def reintentar(self) -> ResumenReintento:
        """Reintenta todos los XMLs en errors/.

        Para cada error: si parsea con éxito, borra el fichero de error y escribe
        en Neo4j. Si falla de nuevo, incrementa `attempts` en el JSON.

        Returns:
            ResumenReintento con recuperados y total_intentados.
        """
        errors_dir = self._cfg.preprocess.errors_dir
        errors_dir.mkdir(parents=True, exist_ok=True)

        error_files = list(errors_dir.glob("*.json"))
        resumen = ResumenReintento(total_intentados=len(error_files))

        with self._driver.session(database=self._db) as s:
            for error_file in error_files:
                error_data = json.loads(error_file.read_text())
                xml_path = Path(error_data["path"])
                try:
                    norma = parse_xml(xml_path, flags=self._cfg.parse)
                    self._upsert_norma(s, norma)
                    for ref in norma.referencias_anteriores:
                        rel_type = self._cfg.relacion.codigos_a_relacion.get(
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
                    error_file.write_text(
                        json.dumps(error_data, ensure_ascii=False)
                    )
                    log.warning(
                        "Reintento fallido", path=str(xml_path), error=str(exc)
                    )

        log.info(
            "\nReintento completado",
            recuperados=resumen.recuperados,
            total=resumen.total_intentados,
        )
        return resumen

    def _persistir_error(self, xml_path: Path, exc: Exception) -> None:
        """Guarda el error de parseo en errors/{stem}.json."""
        errors_dir = self._cfg.preprocess.errors_dir
        errors_dir.mkdir(parents=True, exist_ok=True)
        error_path = errors_dir / f"{xml_path.stem}.json"
        payload = {
            "path": str(xml_path),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(exc),
            "attempts": 1,
        }
        error_path.write_text(json.dumps(payload, ensure_ascii=False))
