"""Fixtures compartidas de pytest."""

from __future__ import annotations

import shutil
from collections.abc import Generator
from pathlib import Path

import pytest

from src.config import APIConfig, PreprocessConfig, Settings


@pytest.fixture()
def boe_test_dir(tmp_path: Path) -> Generator[Path, None, None]:
    """Crea las carpetas raw/ y errors/ en un directorio temporal.

    Se borra automáticamente al finalizar cada test.
    """
    base = tmp_path / "ontology/kinetic-layer/api_boe"
    (base / "raw").mkdir(parents=True)
    (base / "errors").mkdir(parents=True)
    yield base
    shutil.rmtree(base, ignore_errors=True)


@pytest.fixture()
def test_api_config(boe_test_dir: Path) -> APIConfig:
    """APIConfig apuntando al directorio temporal del test."""
    return APIConfig(ontology_dir=boe_test_dir)


@pytest.fixture()
def preprocess_test_dir(tmp_path: Path) -> Generator[Path, None, None]:
    """Crea la carpeta errors/ de preprocesado en un directorio temporal.

    Se borra automáticamente al finalizar cada test.
    """
    base = tmp_path / "ontology"
    (base / "kinetic-layer" / "preprocess" / "errors").mkdir(parents=True)
    yield base
    shutil.rmtree(base, ignore_errors=True)


@pytest.fixture()
def test_preprocess_settings(preprocess_test_dir: Path) -> Settings:
    """Settings con PreprocessConfig apuntando al directorio temporal del test."""
    return Settings(
        preprocess=PreprocessConfig(ontology_dir=preprocess_test_dir)
    )
