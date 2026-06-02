"""
Tests de src/config.py.

Cubren el validador de secretos requeridos (_check_secrets) y la derivación de
rutas de la ontología. El entorno se controla con monkeypatch para no depender
del .env real.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from src.config import APIConfig, PreprocessConfig, Settings


# ── Validador de secretos (_check_secrets) ──────────────────────────────────


def test_check_secrets_falla_sin_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings falla en startup si falta LLM__ANTHROPIC_API_KEY."""
    monkeypatch.delenv("LLM__ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("NEO4J__PASSWORD", "secret")

    with pytest.raises(ValidationError, match="ANTHROPIC_API_KEY"):
        Settings()


def test_check_secrets_falla_sin_password(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings falla en startup si falta NEO4J__PASSWORD."""
    monkeypatch.setenv("LLM__ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("NEO4J__PASSWORD", raising=False)

    with pytest.raises(ValidationError, match="NEO4J__PASSWORD"):
        Settings()


def test_check_secrets_ok_con_ambos_secretos(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings se construye cuando ambos secretos están presentes."""
    monkeypatch.setenv("LLM__ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("NEO4J__PASSWORD", "secret")

    settings = Settings()

    assert settings.llm.anthropic_api_key == "sk-ant-test"
    assert settings.neo4j.password == "secret"


# ── Derivación de rutas ──────────────────────────────────────────────────────


def test_api_config_deriva_rutas_desde_ontology_dir(tmp_path: Path) -> None:
    """APIConfig deriva raw/, errors/ e ids.txt del ontology_dir."""
    config = APIConfig(ontology_dir=tmp_path)

    assert config.raw_dir == tmp_path / "raw"
    assert config.errors_dir == tmp_path / "errors"
    assert config.ids_file == tmp_path / "ids.txt"


def test_preprocess_config_deriva_subdirectorios(tmp_path: Path) -> None:
    """PreprocessConfig deriva los subdirectorios de capa de ontology_dir."""
    config = PreprocessConfig(ontology_dir=tmp_path)

    assert config.semantic_subdir == tmp_path / "semantic-layer"
    assert config.kinetic_subdir == tmp_path / "kinetic-layer"
    assert config.dynamic_subdir == tmp_path / "dynamic-layer"
    assert config.errors_dir == tmp_path / "kinetic-layer" / "preprocess" / "errors"
