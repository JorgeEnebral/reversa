"""Fixtures compartidas de pytest."""

from __future__ import annotations

import shutil
from collections.abc import Generator
from pathlib import Path

import pytest

from src.config import APIConfig


@pytest.fixture()
def boe_test_dir(tmp_path: Path) -> Generator[Path, None, None]:
    """Crea las carpetas raw/ y errors/ en un directorio temporal.

    Se borra automáticamente al finalizar cada test.
    """
    base = tmp_path / "ontology/kinetic-layer/tests/api_boe"
    (base / "raw").mkdir(parents=True)
    (base / "errors").mkdir(parents=True)
    yield base
    shutil.rmtree(base, ignore_errors=True)


@pytest.fixture()
def test_api_config(boe_test_dir: Path) -> APIConfig:
    """APIConfig apuntando al directorio temporal del test."""
    return APIConfig(ontology_dir=boe_test_dir)
