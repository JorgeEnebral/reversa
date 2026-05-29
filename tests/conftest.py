"""Fixtures compartidas de pytest."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from config import APIConfig


@pytest.fixture()
def boe_test_dir(tmp_path: Path) -> Path:  # type: ignore[misc]
    """Crea las carpetas de test y las borra al finalizar."""
    base = tmp_path / "data_api"
    (base / "raw").mkdir(parents=True)
    (base / "errors").mkdir(parents=True)
    yield base
    shutil.rmtree(base, ignore_errors=True)


@pytest.fixture()
def test_api_config(boe_test_dir: Path) -> APIConfig:
    """APIConfig apuntando al directorio temporal de tests."""
    return APIConfig(data_dir=boe_test_dir)
