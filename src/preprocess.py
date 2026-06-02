"""
Preprocesado de XMLs del BOE y carga directa a Neo4j.

Uso:
    preprocesador = Preprocesador()
    resumen = preprocesador.preprocesar_todo()
"""

from __future__ import annotations

import json
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
from src.semantic_schemas import (
    Norma,
    Referencia,
    generar_esquemas,
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
                int(m.get("codigo", "0")) for m in materias_el.findall("materia")
            ]
            norma.materias = [m.text or "" for m in materias_el.findall("materia")]
    if f.notas:
        notas_el = analisis_el.find("notas")
        if notas_el is not None:
            norma.nota = " ".join(n.text or "" for n in notas_el.findall("nota")).strip() or None
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
    if f.referencias_posteriores:
        posteriores = analisis_el.find("referencias/posteriores")
        if posteriores is not None:
            for post in posteriores.findall("posterior"):
                rel_el = post.find("relacion")
                norma.referencias_posteriores.append(
                    Referencia(
                        id_norma=post.findtext("id_norma", ""),
                        relacion_codigo=_int_attr(rel_el, "codigo") or 0,
                        relacion=rel_el.text or "" if rel_el is not None else "",
                        texto=post.findtext("texto", ""),
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
        self.api_raw_dir = config.api.raw_dir
        self._raw_ids: set[str] | None = None
        self._anteriores_faltantes: set[str] = set()
        self._posteriores_faltantes: set[str] = set()

    def preprocesar_todo(self) -> ResumenPreproc:
        """Recorre todos los XMLs en ontology/kinetic-layer/api_boe/raw y los carga en Neo4j.

        Escribe faltantes y genera esquemas al finalizar.

        Returns:
            ResumenPreproc con totales de la operación.
        """
        resumen = ResumenPreproc()
        year_dirs = sorted(p for p in self.api_raw_dir.iterdir() if p.is_dir())
        all_xmls = [f for d in year_dirs for f in sorted(d.glob("*.xml"))]
        self._limpiar_grafo()
        self._raw_ids = None
        self._anteriores_faltantes = set()
        self._posteriores_faltantes = set()

        log.info("\nPreprocesando...")
        with self._driver.session(database=self._db) as s:
            with tqdm(all_xmls, unit="norma", dynamic_ncols=True) as bar:
                for xml_path in bar:
                    bar.set_postfix_str(xml_path.stem, refresh=False)
                    self._procesar_fichero(xml_path, s, resumen)

        self.reintentar()
        self._escribir_faltantes()
        generar_esquemas()
        log.info(
            "\nPreprocesado completado",
            procesadas=resumen.procesadas,
            nodos=resumen.nodos_upsert,
            aristas=resumen.aristas_upsert,
            errores=resumen.errores,
        )
        return resumen

    def _limpiar_grafo(self) -> None:
        """Borra todos los nodos y aristas del grafo antes del procesado masivo."""
        with self._driver.session(database=self._db) as s:
            s.run("MATCH (n) DETACH DELETE n")
        log.info("Grafo limpiado")

    def _procesar_fichero(self, xml_path: Path, session: Any, resumen: ResumenPreproc) -> None:
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
        resumen.aristas_upsert += self._materializar_aristas(
            session, norma, self._ids_consolidados()
        )

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

    def _upsert_relacion(
        self,
        session: Any,
        src_id: str,
        rel_type: str,
        dst_id: str,
        codigo: int,
        texto: str,
    ) -> None:
        """Crea una arista tipada entre dos nodos :Norma.

        Usa MERGE en ambos extremos: si alguno no existe en el corpus se crea
        como stub {id} (nodo sin propiedades). rel_type ya está validado como
        valor en codigos_a_relacion.
        """
        if not src_id or not dst_id:
            return
        query = (
            f"MERGE (a:Norma {{id: $src}})"
            f" MERGE (b:Norma {{id: $dst}})"
            f" CREATE (a)-[:{rel_type} {{codigo: $codigo, texto: $texto}}]->(b)"
        )
        session.run(query, src=src_id, dst=dst_id, codigo=codigo, texto=texto)

    def _ids_consolidados(self) -> set[str]:
        """Devuelve el conjunto de IDs de normas en raw/ (lazy, cacheado por instancia).

        Se usa para la regla de dedup entre anteriores y posteriores.
        """
        if self._raw_ids is None:
            if not self.api_raw_dir.exists():
                self._raw_ids = set()
            else:
                self._raw_ids = {
                    f.stem
                    for d in self.api_raw_dir.iterdir()
                    if d.is_dir()
                    for f in d.glob("*.xml")
                }
        return self._raw_ids

    def _materializar_aristas(self, session: Any, norma: Norma, raw_ids: set[str]) -> int:
        """Crea aristas de anteriores y posteriores. Devuelve número creadas.

        Anteriores: norma → ref. Si ref ∉ raw/, se crea stub y se registra en
        _anteriores_faltantes.
        Posteriores: ref → norma, solo cuando ref ∉ raw/ (dedup: si ref está en
        raw/, su propio <anteriores> ya crea la arista). Los orígenes se registran
        en _posteriores_faltantes.

        Args:
            session: sesión Neo4j activa.
            norma: norma a materializar.
            raw_ids: conjunto de IDs consolidados del corpus.

        Returns:
            Número de aristas creadas.
        """
        n = 0
        codigos = self._cfg.relacion.codigos_a_relacion

        for ref in norma.referencias_anteriores:
            if not ref.id_norma:
                continue
            rel = codigos.get(ref.relacion_codigo)
            if rel:
                self._upsert_relacion(
                    session, norma.id, rel, ref.id_norma, ref.relacion_codigo, ref.texto
                )
                n += 1
                if ref.id_norma not in raw_ids:
                    self._anteriores_faltantes.add(ref.id_norma)

        for ref in norma.referencias_posteriores:
            if not ref.id_norma:
                continue
            if ref.id_norma in raw_ids:
                continue
            rel = codigos.get(ref.relacion_codigo)
            if rel:
                self._upsert_relacion(
                    session, ref.id_norma, rel, norma.id, ref.relacion_codigo, ref.texto
                )
                n += 1
                self._posteriores_faltantes.add(ref.id_norma)

        return n

    def _escribir_faltantes(self) -> None:
        """Escribe anteriores_faltantes.txt y posteriores_faltantes.txt en kinetic-layer/preprocess/."""
        preprocess_dir = self._cfg.preprocess.kinetic_subdir / "preprocess"
        preprocess_dir.mkdir(parents=True, exist_ok=True)
        (preprocess_dir / "anteriores_faltantes.txt").write_text(
            "\n".join(sorted(self._anteriores_faltantes))
        )
        (preprocess_dir / "posteriores_faltantes.txt").write_text(
            "\n".join(sorted(self._posteriores_faltantes))
        )
        log.info(
            "Faltantes escritos",
            anteriores=len(self._anteriores_faltantes),
            posteriores=len(self._posteriores_faltantes),
        )

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
                    self._materializar_aristas(s, norma, self._ids_consolidados())
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
