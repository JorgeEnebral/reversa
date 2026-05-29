"""
Unit tests de BOEDownloader.

Todos los tests usan respx para mockear httpx sin tocar la red.
El fixture test_api_config apunta a un directorio temporal que se borra al final.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import respx
import httpx

from api.downloader import BOEDownloader, _year_from_id


# --------------------------------------------------------------------------- #
# XML de ejemplo mínimo (incluye <fecha_publicacion>)
# --------------------------------------------------------------------------- #
def _make_xml(norm_id: str, fecha: str = "20150730") -> bytes:
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


def _make_listado_page(items: list[dict], total: int | None = None) -> dict:
    """Simula la respuesta JSON del listado."""
    return {"data": items, "total": total or len(items)}


# --------------------------------------------------------------------------- #
# Helpers                                                                     #
# --------------------------------------------------------------------------- #

NORM_ID = "BOE-A-2015-10565"
XML_BYTES = _make_xml(NORM_ID, "20150730")

LISTADO_URL = "https://www.boe.es/datosabiertos/api/legislacion-consolidada"
NORMA_URL = f"https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/{NORM_ID}"


# --------------------------------------------------------------------------- #
# Tests de listado y ordenación                                               #
# --------------------------------------------------------------------------- #


@respx.mock
def test_lista_ids_ordenada_por_fecha(test_api_config):
    """Los IDs se ordenan por fecha_publicacion ASC."""
    items = [
        {"identificador": "BOE-A-2020-1", "fecha_publicacion": "20200101"},
        {"identificador": "BOE-A-1996-1", "fecha_publicacion": "19960515"},
        {"identificador": "BOE-A-2010-1", "fecha_publicacion": "20100301"},
    ]
    respx.get(LISTADO_URL).mock(
        return_value=httpx.Response(200, json=_make_listado_page(items))
    )

    downloader = BOEDownloader(config=test_api_config)
    ids = downloader._obtener_ids_ordenados()

    assert ids == ["BOE-A-1996-1", "BOE-A-2010-1", "BOE-A-2020-1"]


@respx.mock
def test_lista_ids_persiste_en_txt(test_api_config):
    """El listado se persiste en raw/ids.txt, uno por línea."""
    items = [
        {"identificador": "BOE-A-2015-10565", "fecha_publicacion": "20150730"},
    ]
    respx.get(LISTADO_URL).mock(
        return_value=httpx.Response(200, json=_make_listado_page(items))
    )
    # mock norma
    respx.get(NORMA_URL).mock(return_value=httpx.Response(200, content=XML_BYTES))

    downloader = BOEDownloader(config=test_api_config)
    downloader.descargar_masivo()

    ids_file = test_api_config.ids_file
    assert ids_file.exists()
    assert ids_file.read_text().strip() == "BOE-A-2015-10565"


# --------------------------------------------------------------------------- #
# Tests de descarga de norma                                                  #
# --------------------------------------------------------------------------- #


@respx.mock
def test_descarga_id_persiste_en_raw_year(test_api_config):
    """Una descarga exitosa se guarda en raw/2015/BOE-A-2015-10565.xml."""
    items = [{"identificador": NORM_ID, "fecha_publicacion": "20150730"}]
    respx.get(LISTADO_URL).mock(
        return_value=httpx.Response(200, json=_make_listado_page(items))
    )
    respx.get(NORMA_URL).mock(return_value=httpx.Response(200, content=XML_BYTES))

    downloader = BOEDownloader(config=test_api_config)
    downloader.descargar_masivo()

    expected = test_api_config.raw_dir / "2015" / f"{NORM_ID}.xml"
    assert expected.exists()
    assert expected.read_bytes() == XML_BYTES


@respx.mock
def test_descarga_id_404(test_api_config):
    """Un 404 se persiste en errors/{id}.json con status_code 404."""
    items = [{"identificador": NORM_ID, "fecha_publicacion": "20150730"}]
    respx.get(LISTADO_URL).mock(
        return_value=httpx.Response(200, json=_make_listado_page(items))
    )
    respx.get(NORMA_URL).mock(return_value=httpx.Response(404))

    downloader = BOEDownloader(config=test_api_config)
    resumen = downloader.descargar_masivo()

    error_file = test_api_config.errors_dir / f"{NORM_ID}.json"
    assert error_file.exists()
    data = json.loads(error_file.read_text())
    assert data["status_code"] == 404
    assert data["id"] == NORM_ID
    assert resumen.fallidos == 1


@respx.mock
def test_descarga_id_500_no_reintenta_internamente(test_api_config):
    """Un 500 va directo a errors/ sin backoff interno."""
    items = [{"identificador": NORM_ID, "fecha_publicacion": "20150730"}]
    respx.get(LISTADO_URL).mock(
        return_value=httpx.Response(200, json=_make_listado_page(items))
    )
    # respx llama al mock exactamente una vez; si hubiera backoff haría más de una
    respx.get(NORMA_URL).mock(return_value=httpx.Response(500))

    downloader = BOEDownloader(config=test_api_config)
    resumen = downloader.descargar_masivo()

    error_file = test_api_config.errors_dir / f"{NORM_ID}.json"
    assert error_file.exists()
    data = json.loads(error_file.read_text())
    assert data["status_code"] == 500
    assert data["attempts"] == 1
    assert resumen.fallidos == 1


@respx.mock
def test_xml_invalido(test_api_config):
    """XML malformado se persiste en errors/ con error 'XMLSyntaxError'."""
    items = [{"identificador": NORM_ID, "fecha_publicacion": "20150730"}]
    respx.get(LISTADO_URL).mock(
        return_value=httpx.Response(200, json=_make_listado_page(items))
    )
    respx.get(NORMA_URL).mock(
        return_value=httpx.Response(200, content=b"<roto><sin>cerrar")
    )

    downloader = BOEDownloader(config=test_api_config)
    resumen = downloader.descargar_masivo()

    error_file = test_api_config.errors_dir / f"{NORM_ID}.json"
    assert error_file.exists()
    data = json.loads(error_file.read_text())
    assert data["error"]  # cualquier mensaje de error de parseo
    assert resumen.fallidos == 1


@respx.mock
def test_skip_si_ya_descargado(test_api_config):
    """Si el XML ya existe en raw/, no se hace ningún request de norma."""
    # Pre-crear el fichero
    destino = test_api_config.raw_dir / "2015" / f"{NORM_ID}.xml"
    destino.parent.mkdir(parents=True)
    destino.write_bytes(XML_BYTES)

    items = [{"identificador": NORM_ID, "fecha_publicacion": "20150730"}]
    respx.get(LISTADO_URL).mock(
        return_value=httpx.Response(200, json=_make_listado_page(items))
    )
    # NO registramos mock para la norma; si se llama, respx lanzará error

    downloader = BOEDownloader(config=test_api_config)
    resumen = downloader.descargar_masivo()

    assert resumen.saltados == 1
    assert resumen.descargados == 0


# --------------------------------------------------------------------------- #
# Tests de reintentar                                                          #
# --------------------------------------------------------------------------- #


@respx.mock
def test_reintentar_recupera_y_borra(test_api_config):
    """Reintentar con éxito borra el fichero de errors/ y guarda el XML en raw/."""
    error_data = {
        "id": NORM_ID,
        "timestamp": "2026-05-29T08:00:00Z",
        "status_code": 503,
        "error": "Service Unavailable",
        "attempts": 1,
    }
    error_file = test_api_config.errors_dir / f"{NORM_ID}.json"
    error_file.write_text(json.dumps(error_data))

    respx.get(NORMA_URL).mock(return_value=httpx.Response(200, content=XML_BYTES))

    downloader = BOEDownloader(config=test_api_config)
    resumen = downloader.reintentar()

    assert not error_file.exists()
    xml_path = test_api_config.raw_dir / "2015" / f"{NORM_ID}.xml"
    assert xml_path.exists()
    assert resumen.recuperados == 1


@respx.mock
def test_reintentar_reporta_recuperados(test_api_config):
    """reintentar() devuelve los recuperados del total intentados."""
    ok_id = "BOE-A-2015-10565"
    fail_id = "BOE-A-2010-99999"

    for norm_id in [ok_id, fail_id]:
        err = {"id": norm_id, "timestamp": "2026-05-29T08:00:00Z",
               "status_code": 503, "error": "err", "attempts": 1}
        (test_api_config.errors_dir / f"{norm_id}.json").write_text(json.dumps(err))

    ok_url = f"https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/{ok_id}"
    fail_url = f"https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/{fail_id}"

    respx.get(ok_url).mock(
        return_value=httpx.Response(200, content=_make_xml(ok_id, "20150730"))
    )
    respx.get(fail_url).mock(return_value=httpx.Response(500))

    downloader = BOEDownloader(config=test_api_config)
    resumen = downloader.reintentar()

    assert resumen.total_intentados == 2
    assert resumen.recuperados == 1


# --------------------------------------------------------------------------- #
# Tests de descargar_selectivo                                                 #
# --------------------------------------------------------------------------- #


@respx.mock
def test_selectivo_lista(test_api_config):
    """descargar_selectivo descarga solo los IDs indicados, sin pedir el listado."""
    # Si LISTADO_URL fuera llamado, respx lanzaría error (no registrado)
    respx.get(NORMA_URL).mock(return_value=httpx.Response(200, content=XML_BYTES))

    downloader = BOEDownloader(config=test_api_config)
    resumen = downloader.descargar_selectivo([NORM_ID])

    assert resumen.descargados == 1
    assert resumen.fallidos == 0
    expected = test_api_config.raw_dir / "2015" / f"{NORM_ID}.xml"
    assert expected.exists()


# --------------------------------------------------------------------------- #
# Tests auxiliares                                                             #
# --------------------------------------------------------------------------- #


def test_year_from_id_extracts_correctly():
    assert _year_from_id("BOE-A-2015-10565") == "2015"
    assert _year_from_id("BOE-A-1996-15367") == "1996"
    assert _year_from_id("sin-year") == "unknown"
