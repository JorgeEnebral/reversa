"""
Tests del preprocesado: parser XML y carga Neo4j.

Sin tests sobre Neo4j real (una sola instancia en producción). El driver se
mockea con pytest-mock en el import site src.preprocess.GraphDatabase.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.config import (
    AnalisisFlags,
    MetadatosFlags,
    ParseFlags,
    Settings,
    settings,
)
from src.preprocess import (
    Preprocesador,
    generar_esquemas,
    parse_xml,
)
from src.schemas import (
    ResultEdgeSchema,
    UserQuerySchema,
    render_md_edge,
    render_md_norma,
    render_md_result_edge,
    render_md_user_query,
)

FIXTURES = Path(__file__).parent / "fixtures" / "xml"
FIXTURE_39 = FIXTURES / "BOE-A-2015-10565.xml"
FIXTURE_30 = FIXTURES / "BOE-A-1992-26318.xml"


# --------------------------------------------------------------------------- #
# Fixtures                                                                     #
# --------------------------------------------------------------------------- #


@pytest.fixture()
def flags_default() -> ParseFlags:
    """ParseFlags con todos los defaults (igual que settings.parse)."""
    return ParseFlags()


@pytest.fixture()
def mock_driver(mocker: pytest.MockerFixture) -> MagicMock:
    """Mock del driver Neo4j que no abre conexión real."""
    session = MagicMock()
    driver = MagicMock()
    driver.session.return_value.__enter__.return_value = session
    mocker.patch("src.preprocess.GraphDatabase.driver", return_value=driver)
    return driver


# --------------------------------------------------------------------------- #
# Parser: flags True → campos extraídos                                       #
# --------------------------------------------------------------------------- #


def test_parser_aplica_flags_true(flags_default: ParseFlags) -> None:
    """Campos con flag=True se extraen correctamente del XML."""
    norma = parse_xml(FIXTURE_39, flags_default)

    assert norma.id == "BOE-A-2015-10565"
    assert norma.titulo == (
        "Ley 39/2015, de 1 de octubre, del Procedimiento Administrativo "
        "Común de las Administraciones Públicas."
    )
    assert norma.rango_codigo == 1300
    assert norma.rango == "Ley"
    assert norma.fecha_publicacion == "2015-10-02"
    assert norma.diario == "Boletín Oficial del Estado"
    assert norma.departamento_codigo == 3681


def test_parser_ignora_flags_false() -> None:
    """Campos con flag=False no se escriben en el modelo."""
    flags = ParseFlags(
        metadatos=MetadatosFlags(
            titulo=False,
            numero_oficial=False,
            fecha_derogacion=False,
            url_eli=False,
        )
    )
    norma = parse_xml(FIXTURE_39, flags)

    assert norma.titulo is None
    assert norma.numero_oficial is None
    assert norma.fecha_derogacion is None
    assert norma.url_eli is None
    # Campos con True siguen presentes
    assert norma.id == "BOE-A-2015-10565"
    assert norma.rango_codigo == 1300


def test_parser_bloque_padre_false_ignora_hijos() -> None:
    """Si metadatos=False (bool), ningún campo de metadatos se extrae."""
    flags = ParseFlags(metadatos=False)
    norma = parse_xml(FIXTURE_39, flags)

    assert norma.id == "BOE-A-2015-10565"  # id siempre se extrae
    assert norma.titulo is None
    assert norma.rango_codigo is None
    assert norma.vigente is None


def test_parser_vigente_calculado_correctamente(
    flags_default: ParseFlags,
) -> None:
    """vigente=True cuando los tres estatus son 'N'."""
    norma = parse_xml(FIXTURE_39, flags_default)
    assert norma.vigente is True


def test_parser_vigente_false_cuando_derogada(
    flags_default: ParseFlags,
) -> None:
    """vigente=False cuando estatus_derogacion='S'."""
    norma = parse_xml(FIXTURE_30, flags_default)
    assert norma.vigente is False


def test_parser_ignora_referencias_posteriores(
    flags_default: ParseFlags,
) -> None:
    """referencias_anteriores solo contiene las de <anteriores>, nunca <posteriores>."""
    norma = parse_xml(FIXTURE_39, flags_default)

    ids_referenciados = {r.id_norma for r in norma.referencias_anteriores}
    # La posterior de BOE-A-2015-10565 apunta a BOE-A-2020-3824
    assert "BOE-A-2020-3824" not in ids_referenciados


def test_parser_filtra_codigos_no_configurados(
    flags_default: ParseFlags,
) -> None:
    """Código 440 (DE CONFORMIDAD con) está en referencias_anteriores pero no en codigos_a_relacion."""
    norma = parse_xml(FIXTURE_39, flags_default)
    codigos = {r.relacion_codigo for r in norma.referencias_anteriores}
    assert 440 in codigos  # parse_xml NO filtra — lo filtra Preprocesador

    # Verificar que el RelacionConfig no tiene ese código
    assert 440 not in settings.relacion.codigos_a_relacion


def test_parser_extrae_materias(flags_default: ParseFlags) -> None:
    """Materias se extraen como listas paralelas de códigos y textos."""
    norma = parse_xml(FIXTURE_39, flags_default)

    assert norma.materias_codigos == [1270, 1680, 3350]
    assert norma.materias is not None
    assert "Administración Pública" in norma.materias


def test_parser_materias_none_si_flag_false() -> None:
    """materias_codigos es None si AnalisisFlags.materias=False."""
    flags = ParseFlags(analisis=AnalisisFlags(materias=False))
    norma = parse_xml(FIXTURE_39, flags)
    assert norma.materias_codigos is None
    assert norma.materias is None


# --------------------------------------------------------------------------- #
# Parser: fecha y referencias                                                  #
# --------------------------------------------------------------------------- #


def test_parser_fecha_disposicion_formato_iso(
    flags_default: ParseFlags,
) -> None:
    """fecha_disposicion se convierte de YYYYMMDD a YYYY-MM-DD."""
    norma = parse_xml(FIXTURE_39, flags_default)
    assert norma.fecha_disposicion == "2015-10-01"


def test_parser_referencias_anteriores_contiene_cita(
    flags_default: ParseFlags,
) -> None:
    """Código 210 (DEROGA) se parsea en referencias_anteriores."""
    norma = parse_xml(FIXTURE_39, flags_default)
    deroga = next(
        (r for r in norma.referencias_anteriores if r.relacion_codigo == 210),
        None,
    )
    assert deroga is not None
    assert deroga.id_norma == "BOE-A-1992-26318"
    assert "30/1992" in deroga.texto


# --------------------------------------------------------------------------- #
# Orden temporal                                                               #
# --------------------------------------------------------------------------- #


def test_orden_temporal_estable(tmp_path: Path) -> None:
    """Los XMLs se procesan en orden de directorio (alfabético por año + nombre)."""
    import shutil

    year_dir = tmp_path / "1992"
    year_dir.mkdir()
    shutil.copy(FIXTURE_30, year_dir / "BOE-A-1992-26318.xml")
    shutil.copy(FIXTURE_39, tmp_path / "BOE-A-2015-10565.xml")

    year_dirs = sorted(p for p in tmp_path.iterdir() if p.is_dir())
    all_xmls = [f for d in year_dirs for f in sorted(d.glob("*.xml"))]

    assert all_xmls[0].name == "BOE-A-1992-26318.xml"


# --------------------------------------------------------------------------- #
# Regeneración de esquemas semánticos                                         #
# --------------------------------------------------------------------------- #


def test_regenerar_esquemas_borra_y_recrea_semantic_layer(
    tmp_path: Path,
) -> None:
    """semantic-layer se borra y se regenera con nodo norma + aristas."""
    generar_esquemas(base_dir=tmp_path)

    sem = tmp_path / "semantic-layer"
    assert (sem / "humans" / "nodes" / "norma.md").exists()
    assert (sem / "agents" / "nodes" / "norma.json").exists()

    for rel_type in settings.relacion.codigos_a_relacion.values():
        nombre = rel_type.lower()
        assert (sem / "humans" / "edges" / f"{nombre}.md").exists(), (
            f"falta {nombre}.md"
        )
        assert (sem / "agents" / "edges" / f"{nombre}.json").exists()


def test_regenerar_esquemas_sobreescribe_existente(tmp_path: Path) -> None:
    """Una segunda llamada borra el contenido anterior y regenera."""
    generar_esquemas(base_dir=tmp_path)
    stale = tmp_path / "semantic-layer" / "humans" / "nodes" / "stale.md"
    stale.write_text("viejo")

    generar_esquemas(base_dir=tmp_path)
    assert not stale.exists()


def test_regenerar_esquemas_no_toca_dynamic_layer(tmp_path: Path) -> None:
    """dynamic-layer preexistente no se modifica."""
    dyn = tmp_path / "dynamic-layer" / "nodes"
    dyn.mkdir(parents=True)
    custom = dyn / "node.query_usuario.md"
    custom.write_text("# Manual")

    generar_esquemas(base_dir=tmp_path)
    assert custom.read_text() == "# Manual"


def test_regenerar_schema_json_es_valido(tmp_path: Path) -> None:
    """node.norma.schema.json se puede parsear como JSON válido."""
    generar_esquemas(base_dir=tmp_path)
    raw = (
        tmp_path / "semantic-layer" / "agents" / "nodes" / "norma.json"
    ).read_text()
    schema = json.loads(raw)
    assert schema.get("type") == "object"
    assert "properties" in schema


def test_render_md_norma_contiene_id(flags_default: ParseFlags) -> None:
    """El .md de norma siempre contiene la fila del campo id."""
    md = render_md_norma(flags_default)
    assert "| id |" in md
    assert "BOE-A-2015-10565" in md


def test_render_md_norma_vigente_si_estatus_activos() -> None:
    """Fila vigente aparece cuando los 3 flags de estatus están a True."""
    flags = ParseFlags(
        metadatos=MetadatosFlags(
            estatus_derogacion=True,
            estatus_anulacion=True,
            vigencia_agotada=True,
        )
    )
    md = render_md_norma(flags)
    assert "vigente" in md


def test_render_md_norma_vigente_ausente_si_estatus_incompleto() -> None:
    """Fila vigente NO aparece si alguno de los 3 flags de estatus es False."""
    flags = ParseFlags(
        metadatos=MetadatosFlags(
            estatus_derogacion=False,
            estatus_anulacion=True,
            vigencia_agotada=True,
        )
    )
    md = render_md_norma(flags)
    assert "vigente" not in md


def test_render_md_edge_contiene_rel_type() -> None:
    """El .md de arista incluye el TYPE y el código."""
    md = render_md_edge("DEROGA", 210)
    assert "DEROGA" in md
    assert "210" in md


# --------------------------------------------------------------------------- #
# Esquemas dinámicos                                                           #
# --------------------------------------------------------------------------- #


def test_user_query_schema_tiene_user_id_default_unknown() -> None:
    """user_id tiene default 'unknown' cuando no se especifica."""
    q = UserQuerySchema(
        id_nodo="uuid-1",
        user_prompt="¿Qué es la Ley 39/2015?",
        bbdd_query=["MATCH (n:Norma) RETURN n"],
        answer="Es la ley de procedimiento.",
    )
    assert q.user_id == "unknown"


def test_user_query_schema_bbdd_query_es_lista() -> None:
    """bbdd_query acepta múltiples consultas Cypher."""
    q = UserQuerySchema(
        id_nodo="uuid-2",
        user_prompt="Pregunta",
        bbdd_query=["MATCH (a) RETURN a", "MATCH (b) RETURN b"],
        answer="Respuesta",
    )
    assert len(q.bbdd_query) == 2


def test_result_edge_schema_tiene_campo_texto() -> None:
    """ResultEdgeSchema requiere el campo texto."""
    edge = ResultEdgeSchema(texto="Norma que regula el procedimiento")
    assert edge.texto == "Norma que regula el procedimiento"


def test_render_md_user_query_contiene_campos() -> None:
    """El .md de UserQuery incluye los campos clave."""
    md = render_md_user_query()
    assert "UserQuery" in md
    assert "bbdd_query" in md
    assert "user_prompt" in md
    assert "answer" in md


def test_render_md_result_edge_contiene_texto() -> None:
    """El .md de RESULT_EDGE incluye el campo texto."""
    md = render_md_result_edge()
    assert "RESULT_EDGE" in md
    assert "texto" in md


def test_generar_esquemas_incluye_user_query(tmp_path: Path) -> None:
    """generar_esquemas escribe user_query.md y user_query.json."""
    generar_esquemas(base_dir=tmp_path)
    sem = tmp_path / "semantic-layer"
    assert (sem / "humans" / "nodes" / "user_query.md").exists()
    assert (sem / "agents" / "nodes" / "user_query.json").exists()


def test_generar_esquemas_incluye_result_edge(tmp_path: Path) -> None:
    """generar_esquemas escribe result_edge.md y result_edge.json."""
    generar_esquemas(base_dir=tmp_path)
    sem = tmp_path / "semantic-layer"
    assert (sem / "humans" / "edges" / "result_edge.md").exists()
    assert (sem / "agents" / "edges" / "result_edge.json").exists()


def test_generar_esquemas_user_query_json_valido(tmp_path: Path) -> None:
    """user_query.json es JSON Schema válido con additionalProperties:false."""
    generar_esquemas(base_dir=tmp_path)
    raw = (
        tmp_path / "semantic-layer" / "agents" / "nodes" / "user_query.json"
    ).read_text()
    schema = json.loads(raw)
    assert schema.get("type") == "object"
    assert "properties" in schema
    assert schema.get("additionalProperties") is False


# --------------------------------------------------------------------------- #
# Preprocesador con driver mockeado                                           #
# --------------------------------------------------------------------------- #


def test_neo4j_driver_se_instancia_con_config(
    mocker: pytest.MockerFixture, test_preprocess_settings: Settings
) -> None:
    """El Preprocesador llama a GraphDatabase.driver con URI y credenciales de settings."""
    mock_gdb = mocker.patch("src.preprocess.GraphDatabase.driver")

    Preprocesador(config=test_preprocess_settings)

    mock_gdb.assert_called_once_with(
        test_preprocess_settings.neo4j.uri,
        auth=(
            test_preprocess_settings.neo4j.user,
            test_preprocess_settings.neo4j.password,
        ),
    )


def test_preprocesar_limpia_grafo_al_inicio(
    mock_driver: MagicMock, test_preprocess_settings: Settings, tmp_path: Path
) -> None:
    """preprocesar_todo emite DETACH DELETE antes de cualquier MERGE."""
    import shutil

    session = mock_driver.session.return_value.__enter__.return_value

    raw_dir = tmp_path / "2015"
    raw_dir.mkdir(parents=True)
    shutil.copy(FIXTURE_39, raw_dir / "BOE-A-2015-10565.xml")

    prep = Preprocesador(config=test_preprocess_settings)
    prep.api_raw_dir = tmp_path
    prep.preprocesar_todo()

    calls = [str(c.args[0]) for c in session.run.call_args_list]
    delete_idx = next(i for i, c in enumerate(calls) if "DETACH DELETE" in c)
    merge_idx = next(i for i, c in enumerate(calls) if "MERGE (n:Norma" in c)
    assert delete_idx < merge_idx


def test_preprocesar_escribe_norma_con_merge(
    mock_driver: MagicMock, test_preprocess_settings: Settings, tmp_path: Path
) -> None:
    """preprocesar_todo emite una query MERGE sobre :Norma por cada XML."""
    import shutil

    session = mock_driver.session.return_value.__enter__.return_value

    raw_dir = tmp_path / "2015"
    raw_dir.mkdir(parents=True)
    shutil.copy(FIXTURE_39, raw_dir / "BOE-A-2015-10565.xml")

    prep = Preprocesador(config=test_preprocess_settings)
    prep.api_raw_dir = tmp_path
    prep.preprocesar_todo()

    calls = [str(c.args[0]) for c in session.run.call_args_list]
    assert any("MERGE (n:Norma" in c for c in calls)


def test_preprocesar_crea_arista_para_codigo_configurado(
    mock_driver: MagicMock, test_preprocess_settings: Settings, tmp_path: Path
) -> None:
    """Para código 210 (DEROGA) se emite MERGE de arista."""
    import shutil

    session = mock_driver.session.return_value.__enter__.return_value

    raw_dir = tmp_path / "2015"
    raw_dir.mkdir(parents=True)
    shutil.copy(FIXTURE_39, raw_dir / "BOE-A-2015-10565.xml")

    prep = Preprocesador(config=test_preprocess_settings)
    prep.api_raw_dir = tmp_path
    prep.preprocesar_todo()

    calls = [str(c.args[0]) for c in session.run.call_args_list]
    assert any("DEROGA" in c for c in calls)


def test_preprocesar_no_crea_arista_para_codigo_no_configurado(
    mock_driver: MagicMock, test_preprocess_settings: Settings, tmp_path: Path
) -> None:
    """Código 440 (DE CONFORMIDAD con) no genera arista en Neo4j."""
    import shutil

    session = mock_driver.session.return_value.__enter__.return_value

    raw_dir = tmp_path / "2015"
    raw_dir.mkdir(parents=True)
    shutil.copy(FIXTURE_39, raw_dir / "BOE-A-2015-10565.xml")

    prep = Preprocesador(config=test_preprocess_settings)
    prep.api_raw_dir = tmp_path
    prep.preprocesar_todo()

    calls = [str(c) for c in session.run.call_args_list]
    assert not any(
        "EN_RELACION_CON_440" in c or "DE_CONFORMIDAD" in c for c in calls
    )


# --------------------------------------------------------------------------- #
# Errores y reintentos                                                         #
# --------------------------------------------------------------------------- #


def test_error_xml_invalido_persiste_en_errors(
    mock_driver: MagicMock, test_preprocess_settings: Settings, tmp_path: Path
) -> None:
    """XML malformado → error guardado en errors/ con path y attempts=1."""
    raw_dir = tmp_path / "2015"
    raw_dir.mkdir(parents=True)
    bad_xml = raw_dir / "BAD-XML.xml"
    bad_xml.write_bytes(b"<roto><sin>cerrar")

    errors_dir = test_preprocess_settings.preprocess.errors_dir

    prep = Preprocesador(config=test_preprocess_settings)
    prep.api_raw_dir = tmp_path
    resumen = prep.preprocesar_todo()

    assert resumen.errores == 1
    error_files = list(errors_dir.glob("*.json"))
    assert len(error_files) == 1
    data = json.loads(error_files[0].read_text())
    # preprocesar_todo llama a reintentar() internamente → attempts llega a 2
    assert data["attempts"] == 2
    assert "path" in data
    assert "error" in data


def test_reintentar_recupera_fichero_valido(
    mock_driver: MagicMock, test_preprocess_settings: Settings
) -> None:
    """Reintento exitoso: fichero de error desaparece y nodo se escribe en Neo4j."""
    errors_dir = test_preprocess_settings.preprocess.errors_dir
    errors_dir.mkdir(parents=True, exist_ok=True)

    error_data = {
        "path": str(FIXTURE_39),
        "timestamp": "2026-05-30T08:00:00Z",
        "error": "timeout",
        "attempts": 1,
    }
    (errors_dir / "BOE-A-2015-10565.json").write_text(json.dumps(error_data))

    session = mock_driver.session.return_value.__enter__.return_value
    prep = Preprocesador(config=test_preprocess_settings)
    resumen = prep.reintentar()

    assert resumen.recuperados == 1
    assert resumen.total_intentados == 1
    assert not (errors_dir / "BOE-A-2015-10565.json").exists()
    calls = [str(c.args[0]) for c in session.run.call_args_list]
    assert any("MERGE (n:Norma" in c for c in calls)


def test_reintentar_incrementa_attempts_en_fallo(
    mock_driver: MagicMock, test_preprocess_settings: Settings, tmp_path: Path
) -> None:
    """Reintento fallido: attempts sube y fichero de error sigue en errors/."""
    errors_dir = test_preprocess_settings.preprocess.errors_dir
    errors_dir.mkdir(parents=True, exist_ok=True)

    error_data = {
        "path": str(tmp_path / "no_existe.xml"),
        "timestamp": "2026-05-30T08:00:00Z",
        "error": "anterior",
        "attempts": 1,
    }
    error_file = errors_dir / "no_existe.json"
    error_file.write_text(json.dumps(error_data))

    prep = Preprocesador(config=test_preprocess_settings)
    resumen = prep.reintentar()

    assert resumen.recuperados == 0
    assert resumen.total_intentados == 1
    assert error_file.exists()
    data = json.loads(error_file.read_text())
    assert data["attempts"] == 2
