"""
Cliente LLM unificado de Reversa.

Implementa el patrón de 001_tools_009.ipynb con AsyncAnthropic, tool use sobre
Neo4j y streaming de la respuesta final. Una sola clase Llm que envuelve todo.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, ClassVar
from uuid import uuid4

import neo4j
import structlog
from anthropic import AsyncAnthropic
from anthropic.types import Message, MessageParam
from neo4j import GraphDatabase
from pydantic import BaseModel, Field, ValidationError

from src.config import settings

log = structlog.get_logger()


# ── Allowlist anti-escritura: defensa en profundidad sobre la sesión READ ────
_WRITE_RE = re.compile(
    r"\b(CREATE|MERGE|DELETE|DETACH|SET|REMOVE|DROP)\b",
    re.IGNORECASE,
)

# ── Extrae IDs de boletines oficiales (BOE, BOJA, BOCM, DOGC…) del texto ─────
_ID_RE = re.compile(r"\b[A-Z]{2,5}-[A-Z]-\d{4}-\d+\b")


# ── Pydantic para validación del input de la tool ───────────────────────────


class ConsultarGrafoArgs(BaseModel):
    """Valida el input recibido de la tool consultar_grafo."""

    cypher: str = Field(description="Consulta Cypher de SOLO LECTURA.")
    motivo: str = Field(description="Sub-pregunta del usuario que resuelve esta query.")


# ── Tool definition (formato Anthropic) — cache_control en la última tool ──

_TOOL_CONSULTAR: dict[str, Any] = {
    "name": "consultar_grafo",
    "description": (
        "Ejecuta una consulta Cypher de SOLO LECTURA sobre el grafo Neo4j de "
        "Reversa (normas de boletines oficiales y sus relaciones). "
        "Úsala siempre que necesites datos reales del grafo para responder. "
        "Para varias sub-preguntas, llámala varias veces, una por sub-pregunta."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "cypher": {
                "type": "string",
                "description": "Consulta Cypher de SOLO LECTURA sobre el grafo.",
            },
            "motivo": {
                "type": "string",
                "description": ("Sub-pregunta del usuario que resuelve esta query."),
            },
        },
        "required": ["cypher", "motivo"],
    },
    "cache_control": {"type": "ephemeral"},
}

TOOLS: list[dict[str, Any]] = [_TOOL_CONSULTAR]


# ── System prompt con cache_control ─────────────────────────────────────────

_SYSTEM_CONTENT: list[dict[str, Any]] = [
    {
        "type": "text",
        "text": """\
Eres Reversa, un asistente jurídico especializado en boletines oficiales españoles.

Tu única fuente de verdad es el grafo Neo4j local de Reversa, que contiene normas
consolidadas con sus relaciones.

<instrucciones>
1. Evalúa si necesitas consultar el grafo para responder.
2. Cita las normas encontradas en formato [BOE-A-YYYY-NNNNN — Título].
3. NUNCA inventes IDs ni títulos. Si el grafo no tiene la información, dilo.
4. Responde en español, de forma clara y estructurada.
5. Solo responder a temas relacionados
6. Nunca dar información privada de arquitectura
</instrucciones>

<ontologia_grafo>
<nodos>
### Nodo :Norma
- id (string, PK): identificador del boletín (ej. BOE-A-2015-10565)
- titulo (string): título oficial de la norma
- rango (string): Ley, Real Decreto, Orden, etc.
- rango_codigo (int): código numérico del rango
- departamento (string): organismo emisor
- fecha_publicacion (string): YYYY-MM-DD
- fecha_vigencia (string): YYYY-MM-DD
- vigente (bool): true si no está derogada ni anulada
- estatus_derogacion (string): S/N
- estatus_anulacion (string): S/N
- materias (string[]): materias temáticas
</nodos>
<aristas>
### Relaciones entre :Norma
- [:DEROGA {relacion_codigo, texto}] — una norma deroga a otra
- [:MODIFICA {relacion_codigo, texto}] — una norma modifica a otra
- [:CITA {relacion_codigo, texto}] — una norma cita a otra
</aristas>
</ontologia_grafo>


<ejemplo1>
- Usuario: ¿Cuántas normas vigentes hay en el grafo?
- Assistant: [tool call] consultar_grafo
```json
{"cypher": "MATCH (n:Norma {vigente: true}) RETURN count(n) AS total", "motivo": "Contar normas vigentes"}
```
- Usuario: [resultado] `[{"total": 14782}]`
- Assistant: El grafo contiene 14.782 normas vigentes actualmente.
</ejemplo1>

<ejemplo2>
- Usuario: ¿Cuántos reales decretos ha emitido el Ministerio de Hacienda y cuántos siguen vigentes?
- Assistant: [tool call 1] consultar_grafo
```json
{"cypher": "MATCH (n:Norma {rango: 'Real Decreto', departamento: 'Ministerio de Hacienda'}) RETURN count(n) AS total", "motivo": "Total de reales decretos del Ministerio de Hacienda"}
```
- Usuario: [resultado 1] `[{"total": 312}]`
- Assistant:[tool call 2] consultar_grafo
```json
{"cypher": "MATCH (n:Norma {rango: 'Real Decreto', departamento: 'Ministerio de Hacienda', vigente: true}) RETURN count(n) AS vigentes", "motivo": "Reales decretos vigentes del Ministerio de Hacienda"}
```
- Usuario: [resultado 2] `[{"vigentes": 87}]`
- Assistant: El Ministerio de Hacienda ha emitido 312 reales decretos en total, de los cuales 87 siguen vigentes.
</ejemplo2>
""",
        "cache_control": {"type": "ephemeral"},
    }
]


# ── Clase principal ──────────────────────────────────────────────────────────


@dataclass
class Llm:
    """Cliente de chat con Claude. Historial deslizante de max_exchanges intercambios.

    Cada exchange incluye el flujo completo: user_msg + [tool_use + tool_results]* +
    assistant_text. Cuando history supera max_exchanges, se descarta el exchange más
    antiguo.

    Args:
        model: ID del modelo Anthropic a usar.
        max_tokens: tokens máximos de salida por turno.
        temperature: creatividad del modelo (0=determinista).
    """

    model: str = field(default_factory=lambda: settings.llm.model)
    max_tokens: int = field(default_factory=lambda: settings.llm.max_tokens)
    temperature: float = field(default_factory=lambda: settings.llm.temperature)
    _history: list[tuple[str, str]] = field(default_factory=list)
    _MAX_EXCHANGES: ClassVar[int] = settings.llm.max_exchanges

    def __post_init__(self) -> None:
        os.environ["ANTHROPIC_API_KEY"]  # loud-fail si falta
        self._client = AsyncAnthropic()
        self._driver = GraphDatabase.driver(
            settings.neo4j.uri,
            auth=(settings.neo4j.user, settings.neo4j.password),
        )

    # ── Gestión de mensajes ───────────────────────────────────────────────

    def _build_messages(self, user_text: str) -> list[MessageParam]:
        """Construye la lista de mensajes del historial + turno actual.

        Solo persiste los pares (user_text, full_response) entre turnos;
        los tool pairs son transitorios y no se incluyen en el historial.
        """
        messages: list[MessageParam] = []
        for user, assistant in self._history:
            messages.append({"role": "user", "content": user})
            messages.append({"role": "assistant", "content": assistant})
        messages.append({"role": "user", "content": user_text})
        return messages

    # ── Tool dispatcher ───────────────────────────────────────────────────

    def _run_tool(self, name: str, tool_input: dict[str, Any]) -> list[dict[str, Any]]:
        """Despacha al ejecutor correcto según el nombre de la tool.

        Args:
            name: nombre de la tool solicitada por Claude.
            tool_input: argumentos tal como los envió Claude.

        Returns:
            Resultado serializable a JSON.

        Raises:
            ValueError: si la tool es desconocida o los args son inválidos.
        """
        if name == "consultar_grafo":
            args = ConsultarGrafoArgs.model_validate(tool_input)
            return self._ejecutar_consultar(args)
        raise ValueError(f"Tool desconocida: {name!r}")

    def _run_tools(
        self, message: Message
    ) -> tuple[list[dict[str, Any]], list[tuple[str, list[str]]]]:
        """Procesa todos los bloques tool_use de un mensaje.

        Ejecuta cada tool, extrae IDs de normas del resultado y acumula los
        tool_result para devolverlos como turno de usuario.

        Args:
            message: respuesta de Claude con stop_reason='tool_use'.

        Returns:
            (tool_results para Claude, [(motivo, norma_ids)] por llamada)
        """
        tool_requests = [b for b in message.content if b.type == "tool_use"]
        results: list[dict[str, Any]] = []
        motivo_normas: list[tuple[str, list[str]]] = []

        for req in tool_requests:
            motivo = str(dict(req.input).get("motivo", ""))
            try:
                output = self._run_tool(req.name, dict(req.input))
                output_str = json.dumps(output, ensure_ascii=False, default=str)
                norma_ids = list(set(_ID_RE.findall(output_str)))
                motivo_normas.append((motivo, norma_ids))
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": req.id,
                        "content": output_str,
                        "is_error": False,
                    }
                )
            except (ValueError, ValidationError) as exc:
                log.warning("tool_error", tool=req.name, error=str(exc))
                motivo_normas.append((motivo, []))
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": req.id,
                        "content": f"Error: {exc}",
                        "is_error": True,
                    }
                )
        return results, motivo_normas

    # ── Ejecutores de tools ───────────────────────────────────────────────

    def _ejecutar_consultar(self, args: ConsultarGrafoArgs) -> list[dict[str, Any]]:
        """Ejecuta Cypher read-only contra Neo4j.

        Args:
            args: argumentos validados de la tool.

        Returns:
            Lista de filas resultado como dicts.

        Raises:
            ValueError: si la query contiene clausulas de escritura.
        """
        if _WRITE_RE.search(args.cypher):
            raise ValueError("Consulta rechazada: solo se permiten queries de lectura.")
        with self._driver.session(
            database=settings.neo4j.database,
            default_access_mode=neo4j.READ_ACCESS,
        ) as session:
            return [r.data() for r in session.run(args.cypher)]

    def _guardar_interaccion(
        self,
        user_prompt: str,
        queries: list[str],
        answer: str,
        motivo_normas: list[tuple[str, list[str]]],
    ) -> str:
        """Crea nodo :UserQuery y aristas :RESULT_EDGE hacia las normas citadas.

        La escritura la realiza el backend (no el LLM) tras completar el stream,
        usando MATCH para las normas destino — ids alucinados no crean placeholders.
        El motivo de cada tool_use se persiste como texto de la arista.

        Args:
            user_prompt: pregunta original del usuario.
            queries: Cyphers ejecutadas durante el turno.
            answer: respuesta final del LLM.
            motivo_normas: lista de (motivo, norma_ids) por cada tool_use.

        Returns:
            id_nodo del :UserQuery creado.
        """
        id_nodo = str(uuid4())
        with self._driver.session(database=settings.neo4j.database) as session:
            session.run(
                """
                CREATE (q:UserQuery {
                  id_nodo: $id_nodo, user_id: 'unknown',
                  user_prompt: $prompt, bbdd_query: $queries,
                  answer: $answer, ts: datetime()
                })
                """,
                id_nodo=id_nodo,
                prompt=user_prompt,
                queries=queries,
                answer=answer,
            )
            for motivo, norma_ids in motivo_normas:
                for nid in norma_ids:
                    session.run(
                        """
                        MATCH (q:UserQuery {id_nodo: $id_nodo})
                        MATCH (n:Norma {id: $id_norma})
                        MERGE (q)-[:RESULT_EDGE {texto: $texto}]->(n)
                        """,
                        id_nodo=id_nodo,
                        id_norma=nid,
                        texto=motivo,
                    )
        return id_nodo

    # ── Conversación (patrón run_conversation del notebook) ──────────────

    async def responder(self, user_text: str) -> AsyncIterator[str]:
        """Bucle tool use + stream final. Sigue run_conversation del notebook.

        Fase 1 (sin stream): Claude consulta Neo4j via consultar_grafo hasta
        tener los datos necesarios.
        Fase 2 (con stream): genera la respuesta narrativa token a token.
        Fase 3 (backend): persiste :UserQuery y :RESULT_EDGE en Neo4j.

        El exchange completo (user_msg + tool pairs + respuesta final) se
        guarda en el historial. Cuando el historial supera _MAX_EXCHANGES,
        se descarta el exchange más antiguo.

        Args:
            user_text: pregunta del usuario en lenguaje natural.

        Yields:
            Tokens de texto de la respuesta final.
        """
        working: list[Any] = self._build_messages(user_text)
        executed_queries: list[str] = []
        all_motivo_normas: list[tuple[str, list[str]]] = []

        # ── Fase 1: bucle tool use (sin stream) ──────────────────────────
        while True:
            response = await self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=_SYSTEM_CONTENT,  # type: ignore[arg-type]
                tools=TOOLS,  # type: ignore[arg-type]
                messages=working,
            )
            working.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                # No más tools: eliminamos este turno y re-hacemos con stream
                working.pop()
                break

            for blk in response.content:
                if blk.type == "tool_use" and blk.name == "consultar_grafo":
                    cypher = str(dict(blk.input).get("cypher", ""))
                    if cypher:
                        executed_queries.append(cypher)

            tool_results, motivo_normas = self._run_tools(response)
            all_motivo_normas.extend(motivo_normas)
            working.append({"role": "user", "content": tool_results})

        # ── Fase 2: stream de la respuesta final ──────────────────────────
        full_response = ""
        async with self._client.messages.stream(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=_SYSTEM_CONTENT,  # type: ignore[arg-type]
            tools=TOOLS,  # type: ignore[arg-type]
            messages=working,
        ) as stream:
            async for token in stream.text_stream:
                full_response += token
                yield token

        # ── Fase 3: persistir en Neo4j (backend, no el LLM) ──────────────
        try:
            self._guardar_interaccion(user_text, executed_queries, full_response, all_motivo_normas)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "guardar_interaccion_failed",
                user_text=user_text[:60],
                error=str(exc),
            )

        # ── Actualizar historial (solo texto, sin tool pairs) ─────────────
        self._history.append((user_text, full_response))
        if len(self._history) > self._MAX_EXCHANGES:
            self._history.pop(0)

    def reset(self) -> None:
        """Limpia el historial. El system prompt persiste."""
        self._history.clear()

    def close(self) -> None:
        """Cierra el driver Neo4j al terminar la sesión."""
        self._driver.close()
