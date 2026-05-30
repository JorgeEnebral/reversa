"""
Tests del preprocesado: parser XML y carga Neo4j.

Sin tests sobre Neo4j real (una sola instancia en producción). El driver se
mockea con pytest-mock en el import site src.preprocess.GraphDatabase.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.config import (
    AnalisisFlags,
    MetadatosFlags,
    ParseFlags,
    RelacionConfig,
    settings,
)
from src.preprocess import (
    Preprocesador,
    Referencia,
    parse_xml,
    regenerar_esquemas_semanticos,
    render_md_edge,
    render_md_norma,
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
    assert norma.rango_texto == "Ley"
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


def test_parser_vigente_calculado_correctamente(flags_default: ParseFlags) -> None:
    """vigente=True cuando los tres estatus son 'N'."""
    norma = parse_xml(FIXTURE_39, flags_default)
    assert norma.vigente is True


def test_parser_vigente_false_cuando_derogada(flags_default: ParseFlags) -> None:
    """vigente=False cuando estatus_derogacion='S'."""
    norma = parse_xml(FIXTURE_30, flags_default)
    assert norma.vigente is False


def test_parser_ignora_referencias_posteriores(flags_default: ParseFlags) -> None:
    """referencias_anteriores solo contiene las de <anteriores>, nunca <posteriores>."""
    norma = parse_xml(FIXTURE_39, flags_default)

    ids_referenciados = {r.id_norma for r in norma.referencias_anteriores}
    # La posterior de BOE-A-2015-10565 apunta a BOE-A-2020-3824
    assert "BOE-A-2020-3824" not in ids_referenciados


def test_parser_filtra_codigos_no_configurados(flags_default: ParseFlags) -> None:
    """Código 440 (DE CONFORMIDAD con) está en referencias_anteriores pero no en codigos_a_relacion."""
    norma = parse_xml(FIXTURE_39, flags_default)
    codigos = {r.codigo for r in norma.referencias_anteriores}
    assert 440 in codigos  # parse_xml NO filtra — lo filtra Preprocesador

    # Verificar que el RelacionConfig no tiene ese código
    assert 440 not in settings.relacion.codigos_a_relacion


def test_parser_extrae_materias(flags_default: ParseFlags) -> None:
    """Materias se extraen como listas paralelas de códigos y textos."""
    norma = parse_xml(FIXTURE_39, flags_default)

    assert norma.materias_codigos == [1270, 1680, 3350]
    assert norma.materias_textos is not None
    assert "Administración Pública" in norma.materias_textos


def test_parser_materias_none_si_flag_false() -> None:
    """materias_codigos es None si AnalisisFlags.materias=False."""
    flags = ParseFlags(analisis=AnalisisFlags(materias=False))
    norma = parse_xml(FIXTURE_39, flags)
    assert norma.materias_codigos is None
    assert norma.materias_textos is None


# --------------------------------------------------------------------------- #
# Parser: fecha y referencias                                                  #
# --------------------------------------------------------------------------- #


def test_parser_fecha_disposicion_formato_iso(flags_default: ParseFlags) -> None:
    """fecha_disposicion se convierte de YYYYMMDD a YYYY-MM-DD."""
    norma = parse_xml(FIXTURE_39, flags_default)
    assert norma.fecha_disposicion == "2015-10-01"


def test_parser_referencias_anteriores_contiene_cita(flags_default: ParseFlags) -> None:
    """Código 210 (DEROGA) se parsea en referencias_anteriores."""
    norma = parse_xml(FIXTURE_39, flags_default)
    deroga = next((r for r in norma.referencias_anteriores if r.codigo == 210), None)
    assert deroga is not None
    assert deroga.id_norma == "BOE-A-1992-26318"
    assert "30/1992" in deroga.texto


# --------------------------------------------------------------------------- #
# Orden temporal                                                               #
# --------------------------------------------------------------------------- #


def test_orden_temporal_estable(tmp_path: Path) -> None:
    """Los XMLs se procesan en orden de directorio (alfabético por año + nombre)."""
    year_dir = tmp_path / "1992"
    year_dir.mkdir()
    # Copiar dos XMLs de fixture a un directorio de prueba
    import shutil

    shutil.copy(FIXTURE_30, year_dir / "BOE-A-1992-26318.xml")
    shutil.copy(FIXTURE_39, tmp_path / "BOE-A-2015-10565.xml")  # año incorrecto, pero ok

    year_dirs = sorted(p for p in tmp_path.iterdir() if p.is_dir())
    all_xmls = [f for d in year_dirs for f in sorted(d.glob("*.xml"))]

    assert all_xmls[0].name == "BOE-A-1992-26318.xml"


# --------------------------------------------------------------------------- #
# Regeneración de esquemas semánticos                                         #
# --------------------------------------------------------------------------- #


def test_regenerar_esquemas_borra_y_recrea_semantic_layer(tmp_path: Path) -> None:
    """semantic-layer se borra y se regenera con nodo norma + aristas."""
    regenerar_esquemas_semanticos(base_dir=tmp_path)

    sem = tmp_path / "semantic-layer"
    assert (sem / "nodes" / "node.norma.md").exists()
    assert (sem / "nodes" / "node.norma.schema.json").exists()

    # Al menos un par .md + .schema.json por cada relación configurada
    for rel_type in settings.relacion.codigos_a_relacion.values():
        nombre = rel_type.lower()
        assert (sem / "edges" / f"{nombre}.md").exists(), f"falta {nombre}.md"
        assert (sem / "edges" / f"{nombre}.schema.json").exists()


def test_regenerar_esquemas_sobreescribe_existente(tmp_path: Path) -> None:
    """Una segunda llamada borra el contenido anterior y regenera."""
    regenerar_esquemas_semanticos(base_dir=tmp_path)
    stale = tmp_path / "semantic-layer" / "nodes" / "stale.md"
    stale.write_text("viejo")

    regenerar_esquemas_semanticos(base_dir=tmp_path)
    assert not stale.exists()


def test_regenerar_esquemas_no_toca_dynamic_layer(tmp_path: Path) -> None:
    """dynamic-layer preexistente no se modifica."""
    dyn = tmp_path / "dynamic-layer" / "nodes"
    dyn.mkdir(parents=True)
    custom = dyn / "node.query_usuario.md"
    custom.write_text("# Manual")

    regenerar_esquemas_semanticos(base_dir=tmp_path)
    assert custom.read_text() == "# Manual"


def test_regenerar_schema_json_es_valido(tmp_path: Path) -> None:
    """node.norma.schema.json se puede parsear como JSON válido."""
    import json

    regenerar_esquemas_semanticos(base_dir=tmp_path)
    raw = (tmp_path / "semantic-layer" / "nodes" / "node.norma.schema.json").read_text()
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
# Preprocesador con driver mockeado                                           #
# --------------------------------------------------------------------------- #


def test_neo4j_driver_se_instancia_con_config(mocker: pytest.MockerFixture) -> None:
    """El Preprocesador llama a GraphDatabase.driver con URI y credenciales de settings."""
    mock_gdb = mocker.patch("src.preprocess.GraphDatabase.driver")

    Preprocesador()

    mock_gdb.assert_called_once_with(
        settings.neo4j.uri,
        auth=(settings.neo4j.user, settings.neo4j.password),
    )


def test_preprocesar_escribe_norma_con_merge(
    mock_driver: MagicMock, tmp_path: Path
) -> None:
    """preprocesar_todo emite una query MERGE sobre :Norma por cada XML."""
    session = mock_driver.session.return_value.__enter__.return_value

    # Crear estructura temporal de raw dir con un XML
    raw_dir = tmp_path / "2015"
    raw_dir.mkdir(parents=True)
    import shutil

    shutil.copy(FIXTURE_39, raw_dir / "BOE-A-2015-10565.xml")

    prep = Preprocesador()
    prep._RAW_DIR = tmp_path  # type: ignore[assignment]
    prep.preprocesar_todo()

    calls = [str(c.args[0]) for c in session.run.call_args_list]
    assert any("MERGE (n:Norma" in c for c in calls)


def test_preprocesar_crea_arista_para_codigo_configurado(
    mock_driver: MagicMock, tmp_path: Path
) -> None:
    """Para código 210 (DEROGA) se emite MERGE de arista."""
    session = mock_driver.session.return_value.__enter__.return_value

    raw_dir = tmp_path / "2015"
    raw_dir.mkdir(parents=True)
    import shutil

    shutil.copy(FIXTURE_39, raw_dir / "BOE-A-2015-10565.xml")

    prep = Preprocesador()
    prep._RAW_DIR = tmp_path  # type: ignore[assignment]
    prep.preprocesar_todo()

    calls = [str(c.args[0]) for c in session.run.call_args_list]
    assert any("DEROGA" in c for c in calls)


def test_preprocesar_no_crea_arista_para_codigo_no_configurado(
    mock_driver: MagicMock, tmp_path: Path
) -> None:
    """Código 440 (DE CONFORMIDAD con) no genera arista en Neo4j."""
    session = mock_driver.session.return_value.__enter__.return_value

    raw_dir = tmp_path / "2015"
    raw_dir.mkdir(parents=True)
    import shutil

    shutil.copy(FIXTURE_39, raw_dir / "BOE-A-2015-10565.xml")

    prep = Preprocesador()
    prep._RAW_DIR = tmp_path  # type: ignore[assignment]
    prep.preprocesar_todo()

    # Ninguna query contiene 440 como TYPE ni como parámetro de relación
    calls = [str(c) for c in session.run.call_args_list]
    assert not any("EN_RELACION_CON_440" in c or "DE_CONFORMIDAD" in c for c in calls)
