"""
Tests de src/llm.py.

Sin conexiones reales: el driver Neo4j y AsyncAnthropic se mockean.
Sigue las convenciones de tests/test_preprocess.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from src.llm import (
    _BOE_ID_RE,
    _WRITE_RE,
    ConsultarGrafoArgs,
    Llm,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def mock_neo4j_driver(mocker):
    """Mockea GraphDatabase.driver para evitar conexiones reales."""
    return mocker.patch("src.llm.GraphDatabase.driver", return_value=MagicMock())


@pytest.fixture()
def mock_env_key(monkeypatch):
    """Inyecta ANTHROPIC_API_KEY en el entorno para que __post_init__ no falle."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")


@pytest.fixture()
def mock_async_anthropic(mocker):
    """Mockea AsyncAnthropic para evitar llamadas a la API real."""
    return mocker.patch("src.llm.AsyncAnthropic", return_value=MagicMock())


@pytest.fixture()
def llm(mock_neo4j_driver, mock_env_key, mock_async_anthropic):
    """Instancia de Llm con todas las dependencias externas mockeadas."""
    return Llm()


# ── Tests de allowlist anti-escritura ─────────────────────────────────────


class TestAllowlist:
    """Verifica que _WRITE_RE rechaza clausulas de escritura Cypher."""

    @pytest.mark.parametrize(
        "query",
        [
            "CREATE (n:Norma {id: 'test'})",
            "MERGE (n:Norma {id: 'test'})",
            "DELETE n",
            "DETACH DELETE n",
            "SET n.titulo = 'x'",
            "REMOVE n.titulo",
            "DROP INDEX norma_id",
        ],
    )
    def test_write_re_detecta_escritura(self, query: str) -> None:
        """_WRITE_RE debe detectar clausulas de escritura."""
        assert _WRITE_RE.search(query) is not None

    @pytest.mark.parametrize(
        "query",
        [
            "MATCH (n:Norma) RETURN n LIMIT 5",
            "MATCH (a)-[:MODIFICA]->(b) RETURN a.id, b.id",
            "WITH 1 AS x RETURN x",
        ],
    )
    def test_write_re_acepta_lectura(self, query: str) -> None:
        """_WRITE_RE no debe dispararse con queries de solo lectura."""
        assert _WRITE_RE.search(query) is None


# ── Tests de consultar_grafo ───────────────────────────────────────────────


class TestConsultarGrafo:
    """Verifica el comportamiento del ejecutor de consultas Neo4j."""

    def test_rechaza_escritura(self, llm: Llm) -> None:
        """consultar_grafo lanza ValueError si la Cypher contiene CREATE."""
        args = ConsultarGrafoArgs(
            cypher="CREATE (n:Norma {id: 'x'})", motivo="test"
        )
        with pytest.raises(ValueError, match="lectura"):
            llm._ejecutar_consultar(args)

    def test_usa_sesion_read_only(self, llm: Llm, mocker) -> None:
        """consultar_grafo abre sesión con READ_ACCESS."""
        import neo4j

        session_mock = MagicMock()
        session_mock.__enter__ = MagicMock(return_value=session_mock)
        session_mock.__exit__ = MagicMock(return_value=False)
        session_mock.run.return_value = []
        llm._driver.session.return_value = session_mock

        args = ConsultarGrafoArgs(
            cypher="MATCH (n:Norma) RETURN n LIMIT 1", motivo="test"
        )
        llm._ejecutar_consultar(args)

        call_kwargs = llm._driver.session.call_args.kwargs
        assert call_kwargs.get("default_access_mode") == neo4j.READ_ACCESS

    def test_valida_args_con_pydantic(self) -> None:
        """ConsultarGrafoArgs rechaza inputs que no tienen cypher."""
        with pytest.raises(ValidationError):
            ConsultarGrafoArgs.model_validate({"motivo": "sin cypher"})


# ── Tests del bucle tool use ──────────────────────────────────────────────


class TestBucleToolUse:
    """Verifica la lógica del bucle run_conversation (patrón notebook)."""

    @pytest.mark.asyncio
    async def test_bucle_para_sin_tool_use(self, llm: Llm) -> None:
        """responder() no itera si el primer response es end_turn (sin tools)."""
        # Simular una respuesta final sin tool_use
        final_block = MagicMock()
        final_block.type = "text"
        final_block.text = "Respuesta directa sin consultas."

        create_resp = MagicMock()
        create_resp.stop_reason = "end_turn"
        create_resp.content = [final_block]

        # stream mock
        stream_ctx = AsyncMock()
        stream_ctx.__aenter__ = AsyncMock(return_value=stream_ctx)
        stream_ctx.__aexit__ = AsyncMock(return_value=False)
        stream_ctx.text_stream = _async_iter(["Respuesta directa sin consultas."])

        llm._client.messages.create = AsyncMock(return_value=create_resp)
        llm._client.messages.stream = MagicMock(return_value=stream_ctx)

        # Silenciar guardar_interaccion
        llm._guardar_interaccion = MagicMock(return_value="uuid-test")

        tokens = []
        async for tok in llm.responder("¿Cuántas normas hay?"):
            tokens.append(tok)

        # Solo una llamada create (el bucle rompió en la primera iteración)
        llm._client.messages.create.assert_called_once()
        assert "".join(tokens) == "Respuesta directa sin consultas."

    @pytest.mark.asyncio
    async def test_varias_subpreguntas_varias_llamadas(self, llm: Llm) -> None:
        """Varias sub-preguntas generan varias llamadas a consultar_grafo."""
        tool_block_1 = MagicMock()
        tool_block_1.type = "tool_use"
        tool_block_1.id = "tu_1"
        tool_block_1.name = "consultar_grafo"
        tool_block_1.input = {
            "cypher": "MATCH (n:Norma) RETURN count(n)",
            "motivo": "sub-pregunta 1",
        }

        tool_block_2 = MagicMock()
        tool_block_2.type = "tool_use"
        tool_block_2.id = "tu_2"
        tool_block_2.name = "consultar_grafo"
        tool_block_2.input = {
            "cypher": "MATCH (a)-[:DEROGA]->(b) RETURN count(*)",
            "motivo": "sub-pregunta 2",
        }

        resp_tool_use = MagicMock()
        resp_tool_use.stop_reason = "tool_use"
        resp_tool_use.content = [tool_block_1, tool_block_2]

        final_block = MagicMock()
        final_block.type = "text"
        final_block.text = "Hay X normas."

        resp_final = MagicMock()
        resp_final.stop_reason = "end_turn"
        resp_final.content = [final_block]

        # Primera llamada devuelve tool_use con 2 bloques, segunda devuelve end_turn
        llm._client.messages.create = AsyncMock(
            side_effect=[resp_tool_use, resp_final]
        )

        session_mock = MagicMock()
        session_mock.__enter__ = MagicMock(return_value=session_mock)
        session_mock.__exit__ = MagicMock(return_value=False)
        session_mock.run.return_value = [MagicMock(data=lambda: {"count": 42})]
        llm._driver.session.return_value = session_mock

        stream_ctx = AsyncMock()
        stream_ctx.__aenter__ = AsyncMock(return_value=stream_ctx)
        stream_ctx.__aexit__ = AsyncMock(return_value=False)
        stream_ctx.text_stream = _async_iter(["Hay X normas."])
        llm._client.messages.stream = MagicMock(return_value=stream_ctx)

        llm._guardar_interaccion = MagicMock(return_value="uuid-test")

        tokens = []
        async for tok in llm.responder("¿Cuántas normas? ¿Cuántas derogaciones?"):
            tokens.append(tok)

        # Dos llamadas: una con tool_use (2 bloques), otra con end_turn
        assert llm._client.messages.create.call_count == 2
        assert "".join(tokens) == "Hay X normas."

    @pytest.mark.asyncio
    async def test_guardar_interaccion_tras_stream(self, llm: Llm) -> None:
        """guardar_interaccion se llama exactamente una vez al finalizar."""
        create_resp = MagicMock()
        create_resp.stop_reason = "end_turn"
        create_resp.content = []
        llm._client.messages.create = AsyncMock(return_value=create_resp)

        stream_ctx = AsyncMock()
        stream_ctx.__aenter__ = AsyncMock(return_value=stream_ctx)
        stream_ctx.__aexit__ = AsyncMock(return_value=False)
        stream_ctx.text_stream = _async_iter(
            ["Ver [BOE-A-2015-10565 — Ley 39/2015]."]
        )
        llm._client.messages.stream = MagicMock(return_value=stream_ctx)

        guardar_mock = MagicMock(return_value="uuid-001")
        llm._guardar_interaccion = guardar_mock

        async for _ in llm.responder("pregunta de prueba"):
            pass

        guardar_mock.assert_called_once()
        _, _, answer, norma_ids = guardar_mock.call_args.args
        assert "BOE-A-2015-10565" in norma_ids


# ── Tests de extracción de IDs BOE ────────────────────────────────────────


class TestBoeidRe:
    """Verifica la regex de extracción de IDs BOE del texto libre."""

    def test_extrae_id_valido(self) -> None:
        text = "Ver [BOE-A-2015-10565 — Ley 39/2015]."
        assert _BOE_ID_RE.findall(text) == ["BOE-A-2015-10565"]

    def test_extrae_multiples_ids(self) -> None:
        text = "BOE-A-1992-26318 y BOE-A-2015-10566 son relevantes."
        ids = _BOE_ID_RE.findall(text)
        assert "BOE-A-1992-26318" in ids
        assert "BOE-A-2015-10566" in ids

    def test_ignora_texto_sin_ids(self) -> None:
        assert _BOE_ID_RE.findall("Sin normas concretas.") == []


# ── Tests de historial deslizante ─────────────────────────────────────────


class TestHistorial:
    """Verifica que el historial no supera los 5 intercambios."""

    @pytest.mark.asyncio
    async def test_historial_no_supera_max(self, llm: Llm) -> None:
        """Después de 7 turnos el historial tiene como máximo 5 entradas."""
        create_resp = MagicMock()
        create_resp.stop_reason = "end_turn"
        create_resp.content = []
        llm._client.messages.create = AsyncMock(return_value=create_resp)

        for i in range(7):
            stream_ctx = AsyncMock()
            stream_ctx.__aenter__ = AsyncMock(return_value=stream_ctx)
            stream_ctx.__aexit__ = AsyncMock(return_value=False)
            stream_ctx.text_stream = _async_iter([f"respuesta {i}"])
            llm._client.messages.stream = MagicMock(return_value=stream_ctx)
            llm._guardar_interaccion = MagicMock(return_value="uuid")

            async for _ in llm.responder(f"pregunta {i}"):
                pass

        assert len(llm._history) <= llm._MAX_EXCHANGES

    def test_reset_limpia_historial(self, llm: Llm) -> None:
        """reset() vacía el historial."""
        llm._history.append(("user", "assistant"))
        llm.reset()
        assert llm._history == []


# ── Helper async ─────────────────────────────────────────────────────────────


async def _async_iter(items):
    """Genera un iterador asíncrono a partir de una lista."""
    for item in items:
        yield item
