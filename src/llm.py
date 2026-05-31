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
from typing import Any
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

# ── Extrae IDs BOE del texto libre de la respuesta ─────────────────────────
_BOE_ID_RE = re.compile(r"\bBOE-[A-Z]+-\d{4}-\d+\b")


# ── Pydantic para validación del input de la tool ───────────────────────────


class ConsultarGrafoArgs(BaseModel):
    """Valida el input recibido de la tool consultar_grafo."""

    cypher: str = Field(description="Consulta Cypher de SOLO LECTURA.")
    motivo: str = Field(
        description="Sub-pregunta del usuario que resuelve esta query."
    )


# ── Tool definition (formato Anthropic — igual que en 001_tools_009.ipynb) ──

_TOOL_CONSULTAR: dict[str, Any] = {
    "name": "consultar_grafo",
    "description": (
        "Ejecuta una consulta Cypher de SOLO LECTURA sobre el grafo Neo4j de "
        "Reversa (normas BOE y sus relaciones: DEROGA, MODIFICA, CITA). "
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
                "description": (
                    "Sub-pregunta del usuario que resuelve esta query."
                ),
            },
        },
        "required": ["cypher", "motivo"],
    },
}

TOOLS: list[dict[str, Any]] = [_TOOL_CONSULTAR]


# ── System prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
Eres Reversa, un asistente jurídico especializado en el Boletín Oficial del Estado.

Tu única fuente de verdad es el grafo Neo4j local de Reversa, que contiene normas
consolidadas del BOE con sus relaciones. Usa la tool consultar_grafo para obtener
datos reales antes de responder.

## Esquema del grafo

### Nodo :Norma
- id (string, PK): identificador BOE, ej. BOE-A-2015-10565
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

### Relaciones entre :Norma
- [:DEROGA {relacion_codigo, texto}] — una norma deroga a otra
- [:MODIFICA {relacion_codigo, texto}] — una norma modifica a otra
- [:CITA {relacion_codigo, texto}] — una norma cita a otra

## Ejemplos de Cypher útiles (4 briefings del Consejo)

```cypher
// Briefing 1 — top 5 normas más modificadas (más modificaciones recibidas)
MATCH (a:Norma)-[:MODIFICA]->(b:Norma)
RETURN b.id AS norma, b.titulo AS titulo, count(*) AS n_modificaciones
ORDER BY n_modificaciones DESC LIMIT 5

// Briefing 2 — top 5 normas que más modifican (más modificaciones emitidas)
MATCH (a:Norma)-[:MODIFICA]->(b:Norma)
RETURN a.id AS norma, a.titulo AS titulo, count(*) AS n_realizadas
ORDER BY n_realizadas DESC LIMIT 5

// Briefing 3 — normas vivas que citan normas derogadas
MATCH (viva:Norma {vigente:true})-[:CITA]->(muerta:Norma {vigente:false})
RETURN viva.id, viva.titulo, count(muerta) AS refs_muertas
ORDER BY refs_muertas DESC LIMIT 10

// Briefing 4 — blast radius Ley 30/1992 (normas vivas que la citan)
MATCH (viva:Norma {vigente:true})-[:CITA]->(:Norma {id:'BOE-A-1992-26318'})
RETURN viva.id, viva.titulo
```

## Instrucciones

1. Evalúa si necesitas consultar el grafo para responder. Si sí, llama a consultar_grafo.
2. Para preguntas con varias sub-preguntas, llama a consultar_grafo varias veces.
3. Cita las normas encontradas en formato [BOE-A-YYYY-NNNNN — Título].
4. NUNCA inventes IDs ni títulos. Si el grafo no tiene la información, dilo.
5. Responde en español, de forma clara y estructurada.
"""


# ── Clase principal ──────────────────────────────────────────────────────────


@dataclass
class Llm:
    """Cliente de chat con Claude. Historial deslizante de 5 intercambios.

    Sigue el patrón de 001_tools_009.ipynb adaptado a AsyncAnthropic.
    El historial guarda solo los pares (user_text, assistant_text);
    los tool pairs transitorios no se persisten entre turnos.

    Args:
        model: ID del modelo Anthropic a usar.
        max_tokens: tokens máximos de salida por turno.
        temperature: creatividad del modelo (0=determinista).
        max_tool_iters: tope del bucle tool use por turno.
        system_prompt: instrucciones de sistema.

    Attributes:
        _history: lista de (user_text, assistant_text) previos.
    """

    model: str = field(default_factory=lambda: settings.llm.model)
    max_tokens: int = field(default_factory=lambda: settings.llm.max_tokens)
    temperature: float = field(default_factory=lambda: settings.llm.temperature)
    max_tool_iters: int = field(
        default_factory=lambda: settings.llm.max_tool_iters
    )
    system_prompt: str = SYSTEM_PROMPT
    _history: list[tuple[str, str]] = field(default_factory=list)

    _MAX_EXCHANGES: int = 5  # 5 user + 5 assistant = ventana de 10 mensajes

    def __post_init__(self) -> None:
        os.environ["ANTHROPIC_API_KEY"]  # loud-fail si falta (security.md)
        self._client = AsyncAnthropic()
        self._driver = GraphDatabase.driver(
            settings.neo4j.uri,
            auth=(settings.neo4j.user, settings.neo4j.password),
        )

    # ── Gestión de mensajes (patrón add_*/chat del notebook) ─────────────

    def _build_messages(self, user_text: str) -> list[MessageParam]:
        """Construye la lista de mensajes del historial + turno actual."""
        messages: list[MessageParam] = []
        for user, assistant in self._history:
            messages.append({"role": "user", "content": user})
            messages.append({"role": "assistant", "content": assistant})
        messages.append({"role": "user", "content": user_text})
        return messages

    # ── Tool dispatcher (patrón run_tool del notebook) ────────────────────

    def _run_tool(
        self, name: str, tool_input: dict[str, Any]
    ) -> list[dict[str, Any]]:
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

    def _run_tools(self, message: Message) -> list[dict[str, Any]]:
        """Procesa todos los bloques tool_use de un mensaje.

        Igual que run_tools() del notebook. Ejecuta cada tool y acumula
        los tool_result para devolverlos como turno de usuario.

        Args:
            message: respuesta de Claude con stop_reason='tool_use'.

        Returns:
            Lista de bloques tool_result listos para añadir al historial.
        """
        tool_requests = [b for b in message.content if b.type == "tool_use"]
        results: list[dict[str, Any]] = []
        for req in tool_requests:
            try:
                output = self._run_tool(req.name, req.input)
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": req.id,
                        "content": json.dumps(
                            output, ensure_ascii=False, default=str
                        ),
                        "is_error": False,
                    }
                )
            except (ValueError, ValidationError) as exc:
                log.warning("tool_error", tool=req.name, error=str(exc))
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": req.id,
                        "content": f"Error: {exc}",
                        "is_error": True,
                    }
                )
        return results

    # ── Ejecutores de tools ───────────────────────────────────────────────

    def _ejecutar_consultar(
        self, args: ConsultarGrafoArgs
    ) -> list[dict[str, Any]]:
        """Ejecuta Cypher read-only contra Neo4j.

        Args:
            args: argumentos validados de la tool.

        Returns:
            Lista de filas resultado como dicts.

        Raises:
            ValueError: si la query contiene clausulas de escritura.
        """
        if _WRITE_RE.search(args.cypher):
            raise ValueError(
                "Consulta rechazada: solo se permiten queries de lectura."
            )
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
        norma_ids: list[str],
    ) -> str:
        """Crea nodo :UserQuery y aristas :RESULT_EDGE hacia las normas citadas.

        La escritura la realiza el backend (no el LLM) tras completar el stream,
        usando MATCH para las normas destino — ids alucinados no crean placeholders.

        Args:
            user_prompt: pregunta original del usuario.
            queries: Cyphers ejecutadas durante el turno.
            answer: respuesta final del LLM.
            norma_ids: IDs BOE mencionados en la respuesta.

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
            for nid in norma_ids:
                session.run(
                    """
                    MATCH (q:UserQuery {id_nodo: $id_nodo})
                    MATCH (n:Norma {id: $id_norma})
                    MERGE (q)-[e:RESULT_EDGE]->(n)
                    SET e.texto = 'norma citada en la respuesta'
                    """,
                    id_nodo=id_nodo,
                    id_norma=nid,
                )
        return id_nodo

    # ── Conversación (patrón run_conversation del notebook) ──────────────

    async def responder(self, user_text: str) -> AsyncIterator[str]:
        """Bucle tool use + stream final. Sigue run_conversation del notebook.

        Fase 1 (sin stream): Claude consulta Neo4j via consultar_grafo hasta
        tener los datos necesarios. Fase 2 (con stream): genera la respuesta
        narrativa token a token. Fase 3 (backend): persiste :UserQuery.

        Args:
            user_text: pregunta del usuario en lenguaje natural.

        Yields:
            Tokens de texto de la respuesta final.
        """
        working: list[Any] = self._build_messages(user_text)  # type: ignore[assignment]
        executed_queries: list[str] = []

        # ── Fase 1: bucle tool use (sin stream, patrón notebook) ─────────
        for _ in range(self.max_tool_iters):
            response = await self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system=self.system_prompt,
                tools=TOOLS,  # type: ignore[arg-type]
                messages=working,
            )
            working.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                # No más tools: eliminamos este turno y re-hacemos con stream
                working.pop()
                break

            # Recoger queries ejecutadas para guardar_interaccion
            for blk in response.content:
                if blk.type == "tool_use" and blk.name == "consultar_grafo":
                    cypher = str(blk.input.get("cypher", ""))  # type: ignore[union-attr]
                    if cypher:
                        executed_queries.append(cypher)

            tool_results = self._run_tools(response)
            working.append({"role": "user", "content": tool_results})

        # ── Fase 2: stream de la respuesta final ──────────────────────────
        full_response = ""
        async with self._client.messages.stream(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=self.system_prompt,
            tools=TOOLS,  # type: ignore[arg-type]
            messages=working,
        ) as stream:
            async for token in stream.text_stream:
                full_response += token
                yield token

        # ── Fase 3: persistir en Neo4j (backend, no el LLM) ──────────────
        norma_ids = list(set(_BOE_ID_RE.findall(full_response)))
        try:
            self._guardar_interaccion(
                user_text, executed_queries, full_response, norma_ids
            )
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "guardar_interaccion_failed",
                user_text=user_text[:60],
                error=str(exc),
            )

        # ── Actualizar historial (solo texto, sin tool pairs) ─────────────
        self._history.append((user_text, full_response))
        if len(self._history) > self._MAX_EXCHANGES:
            self._history = self._history[-self._MAX_EXCHANGES :]

    def reset(self) -> None:
        """Limpia el historial. El system prompt persiste."""
        self._history.clear()

    def close(self) -> None:
        """Cierra el driver Neo4j al terminar la sesión."""
        self._driver.close()
