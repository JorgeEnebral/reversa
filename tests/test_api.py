"""
Tests de BOEDownloader.

Secciones:
  UNIT        — httpx mockeado con respx, sin red
  INTEGRATION — requiere internet; marcar con pytest -m integration para ejecutar
"""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from src.api import BOEDownloader, _year_from_id
from src.config import APIConfig

# --------------------------------------------------------------------------- #
# Helpers de fixtures                                                          #
# --------------------------------------------------------------------------- #

BASE = "https://www.boe.es/datosabiertos/api"
LISTADO_URL = f"{BASE}/legislacion-consolidada"
NORM_ID = "BOE-A-2015-10565"
NORMA_URL = f"{BASE}/legislacion-consolidada/id/{NORM_ID}"


def _xml(norm_id: str, fecha: str = "20150730") -> bytes:
    return (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f"<legislacion>"
        f"<metadatos>"
        f"<identificador>{norm_id}</identificador>"
        f"<fecha_publicacion>{fecha}</fecha_publicacion>"
        f"</metadatos>"
        f"<analisis/><texto/>"
        f"</legislacion>"
    ).encode()


def _listado(items: list[dict[str, str]]) -> dict[str, object]:
    return {"data": items, "total": len(items)}


XML_BYTES = _xml(NORM_ID, "20150730")


# --------------------------------------------------------------------------- #
# UNIT                                                                         #
# --------------------------------------------------------------------------- #


@respx.mock
def test_lista_ids_ordenada_por_fecha(test_api_config: APIConfig) -> None:
    """Los IDs se devuelven ordenados por fecha_publicacion ASC."""
    items: list[dict[str, str]] = [
        {"identificador": "BOE-A-2020-1", "fecha_publicacion": "20200101"},
        {"identificador": "BOE-A-1996-1", "fecha_publicacion": "19960515"},
        {"identificador": "BOE-A-2010-1", "fecha_publicacion": "20100301"},
    ]
    respx.get(LISTADO_URL).mock(
        return_value=httpx.Response(200, json=_listado(items))
    )

    ids = BOEDownloader(config=test_api_config)._obtener_ids_ordenados()

    assert ids == ["BOE-A-1996-1", "BOE-A-2010-1", "BOE-A-2020-1"]


@respx.mock
def test_lista_ids_persiste_en_txt(test_api_config: APIConfig) -> None:
    """El listado se persiste en api_boe/ids.txt, un ID por línea."""
    items: list[dict[str, str]] = [
        {"identificador": NORM_ID, "fecha_publicacion": "20150730"}
    ]
    respx.get(LISTADO_URL).mock(
        return_value=httpx.Response(200, json=_listado(items))
    )
    respx.get(NORMA_URL).mock(
        return_value=httpx.Response(200, content=XML_BYTES)
    )

    BOEDownloader(config=test_api_config).descargar_masivo()

    ids_file = test_api_config.ids_file
    assert ids_file.exists()
    assert ids_file.read_text().strip() == NORM_ID


@respx.mock
def test_descarga_id_persiste_en_raw_year(test_api_config: APIConfig) -> None:
    """Descarga exitosa → raw/2015/BOE-A-2015-10565.xml con el contenido correcto."""
    items: list[dict[str, str]] = [
        {"identificador": NORM_ID, "fecha_publicacion": "20150730"}
    ]
    respx.get(LISTADO_URL).mock(
        return_value=httpx.Response(200, json=_listado(items))
    )
    respx.get(NORMA_URL).mock(
        return_value=httpx.Response(200, content=XML_BYTES)
    )

    BOEDownloader(config=test_api_config).descargar_masivo()

    expected = test_api_config.raw_dir / "2015" / f"{NORM_ID}.xml"
    assert expected.exists()
    assert expected.read_bytes() == XML_BYTES


@respx.mock
def test_descarga_id_404(test_api_config: APIConfig) -> None:
    """Un 404 se persiste en errors/{id}.json con status_code 404."""
    items: list[dict[str, str]] = [
        {"identificador": NORM_ID, "fecha_publicacion": "20150730"}
    ]
    respx.get(LISTADO_URL).mock(
        return_value=httpx.Response(200, json=_listado(items))
    )
    respx.get(NORMA_URL).mock(return_value=httpx.Response(404))

    resumen = BOEDownloader(config=test_api_config).descargar_masivo()

    error_file = test_api_config.errors_dir / f"{NORM_ID}.json"
    assert error_file.exists()
    data: dict[str, object] = json.loads(error_file.read_text())
    assert data["status_code"] == 404
    assert data["id"] == NORM_ID
    assert resumen.fallidos == 1


@respx.mock
def test_descarga_id_500_persiste_error(
    test_api_config: APIConfig,
) -> None:
    """Un 500 se persiste en errors/; descargar_masivo reintenta una vez al final."""
    items: list[dict[str, str]] = [
        {"identificador": NORM_ID, "fecha_publicacion": "20150730"}
    ]
    respx.get(LISTADO_URL).mock(
        return_value=httpx.Response(200, json=_listado(items))
    )
    respx.get(NORMA_URL).mock(return_value=httpx.Response(500))

    resumen = BOEDownloader(config=test_api_config).descargar_masivo()

    data: dict[str, object] = json.loads(
        (test_api_config.errors_dir / f"{NORM_ID}.json").read_text()
    )
    # descargar_masivo llama a reintentar() internamente → attempts llega a 2
    assert data["attempts"] == 2
    assert resumen.fallidos == 1


@respx.mock
def test_xml_invalido(test_api_config: APIConfig) -> None:
    """XML malformado → error persistido en errors/."""
    items: list[dict[str, str]] = [
        {"identificador": NORM_ID, "fecha_publicacion": "20150730"}
    ]
    respx.get(LISTADO_URL).mock(
        return_value=httpx.Response(200, json=_listado(items))
    )
    respx.get(NORMA_URL).mock(
        return_value=httpx.Response(200, content=b"<roto><sin>cerrar")
    )

    resumen = BOEDownloader(config=test_api_config).descargar_masivo()

    data: dict[str, object] = json.loads(
        (test_api_config.errors_dir / f"{NORM_ID}.json").read_text()
    )
    assert data["error"]
    assert resumen.fallidos == 1


@respx.mock
def test_skip_si_ya_descargado(test_api_config: APIConfig) -> None:
    """Si el XML ya existe en raw/, no se hace ningún request de norma."""
    destino = test_api_config.raw_dir / "2015" / f"{NORM_ID}.xml"
    destino.parent.mkdir(parents=True)
    destino.write_bytes(XML_BYTES)

    items: list[dict[str, str]] = [
        {"identificador": NORM_ID, "fecha_publicacion": "20150730"}
    ]
    respx.get(LISTADO_URL).mock(
        return_value=httpx.Response(200, json=_listado(items))
    )

    resumen = BOEDownloader(config=test_api_config).descargar_masivo()

    assert resumen.saltados == 1
    assert resumen.descargados == 0


@respx.mock
def test_reintentar_recupera_y_borra(test_api_config: APIConfig) -> None:
    """Reintento exitoso: fichero de error desaparece y XML aparece en raw/."""
    error_data = {
        "id": NORM_ID,
        "timestamp": "2026-05-29T08:00:00Z",
        "status_code": 503,
        "error": "Service Unavailable",
        "attempts": 1,
    }
    (test_api_config.errors_dir / f"{NORM_ID}.json").write_text(
        json.dumps(error_data)
    )
    respx.get(NORMA_URL).mock(
        return_value=httpx.Response(200, content=XML_BYTES)
    )

    resumen = BOEDownloader(config=test_api_config).reintentar()

    assert not (test_api_config.errors_dir / f"{NORM_ID}.json").exists()
    assert (test_api_config.raw_dir / "2015" / f"{NORM_ID}.xml").exists()
    assert resumen.recuperados == 1


@respx.mock
def test_reintentar_reporta_recuperados(test_api_config: APIConfig) -> None:
    """reintentar() devuelve recuperados / total_intentados correctamente."""
    ok_id = "BOE-A-2015-10565"
    fail_id = "BOE-A-2010-99999"

    for norm_id in (ok_id, fail_id):
        err = {
            "id": norm_id,
            "timestamp": "2026-05-29T08:00:00Z",
            "status_code": 503,
            "error": "err",
            "attempts": 1,
        }
        (test_api_config.errors_dir / f"{norm_id}.json").write_text(
            json.dumps(err)
        )

    respx.get(f"{BASE}/legislacion-consolidada/id/{ok_id}").mock(
        return_value=httpx.Response(200, content=_xml(ok_id, "20150730"))
    )
    respx.get(f"{BASE}/legislacion-consolidada/id/{fail_id}").mock(
        return_value=httpx.Response(500)
    )

    resumen = BOEDownloader(config=test_api_config).reintentar()

    assert resumen.total_intentados == 2
    assert resumen.recuperados == 1


@respx.mock
def test_selectivo_lista(test_api_config: APIConfig) -> None:
    """descargar_selectivo descarga solo los IDs dados sin pedir el listado completo."""
    respx.get(NORMA_URL).mock(
        return_value=httpx.Response(200, content=XML_BYTES)
    )

    resumen = BOEDownloader(config=test_api_config).descargar_selectivo(
        [NORM_ID]
    )

    assert resumen.descargados == 1
    assert resumen.fallidos == 0
    assert (test_api_config.raw_dir / "2015" / f"{NORM_ID}.xml").exists()


def test_year_from_id() -> None:
    """_year_from_id extrae el año del identificador BOE."""
    assert _year_from_id("BOE-A-2015-10565") == "2015"
    assert _year_from_id("BOE-A-1996-15367") == "1996"
    assert _year_from_id("sin-year") == "unknown"


# --------------------------------------------------------------------------- #
# INTEGRATION                                                                  #
# --------------------------------------------------------------------------- #


@pytest.mark.integration
def test_descarga_real_norma_conocida(test_api_config: APIConfig) -> None:
    """Descarga Ley 39/2015 contra la API real y verifica estructura del XML."""
    norm_id = "BOE-A-2015-10565"

    resumen = BOEDownloader(config=test_api_config).descargar_selectivo(
        [norm_id]
    )

    assert resumen.descargados == 1
    assert resumen.fallidos == 0

    xml_path = test_api_config.raw_dir / "2015" / f"{norm_id}.xml"
    assert xml_path.exists()
    content = xml_path.read_bytes()
    assert b"<metadatos>" in content
    assert b"<analisis>" in content
    assert b"<texto>" in content
