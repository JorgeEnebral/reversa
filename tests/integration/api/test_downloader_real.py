"""
Integration test contra la API real del BOE.

Requiere conexión a internet. Se salta con -m "not integration" en CI.
Marca: @pytest.mark.integration
"""

from __future__ import annotations

import pytest

from api.downloader import BOEDownloader


@pytest.mark.integration
def test_descarga_real_norma_conocida(test_api_config):
    """Descarga Ley 39/2015 real y verifica estructura del XML."""
    norm_id = "BOE-A-2015-10565"
    downloader = BOEDownloader(config=test_api_config)
    resumen = downloader.descargar_selectivo([norm_id])

    assert resumen.descargados == 1
    assert resumen.fallidos == 0

    xml_path = test_api_config.raw_dir / "2015" / f"{norm_id}.xml"
    assert xml_path.exists()

    content = xml_path.read_bytes()
    assert b"<metadatos>" in content
    assert b"<analisis>" in content
    assert b"<texto>" in content
