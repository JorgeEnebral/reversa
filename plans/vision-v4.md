# Reversa — Plan arquitectónico v4

> v4 sobre [`vision-v3.md`]. Las decisiones aquí **sobrescriben** a las de v3; lo que no se mencione, se mantiene.

## Prompt

Sustituye el enfoque de "routing fijo + `NO uses tools`" del §3.2/§3.3 de v3 por un **agente con tool use nativo de Anthropic**:

- El LLM consulta la BBDD Neo4j por sí mismo mediante una **tool de consulta** (read-only).
- El LLM persiste cada interacción mediante una **tool de escritura** que crea el nodo `:UserQuery` y las aristas `:RESULT_EDGE` hacia las normas resultado.
- Los esquemas **ya están hechos** (`ontology/semantic-layer/`); la tool los usa, no los regenera.

Flujo objetivo:

```
usuario pregunta
  → el LLM evalúa si necesita consultar el grafo para responder
  → usando los esquemas redacta Cypher y llama a la tool de consulta (Neo4j)
  → Neo4j responde, el LLM procesa los resultados
  → el LLM llama a la tool de escritura: crea el nodo :UserQuery
    y las aristas :RESULT_EDGE que lo unen a las normas resultado
```

Si una misma pregunta del usuario contiene **varias sub-preguntas**, el LLM llama a la tool de consulta **varias veces** (un `tool_use` por sub-pregunta).

---

## 1. Qué se sustituye respecto a v3

| v3 (queda obsoleto) | v4 (lo nuevo) |
|---|---|
| §3.2: backend detecta keywords de las 4 briefings (regex/fuzzy) → ejecuta Cypher fija → inyecta `<resultado_grafo>` | El LLM **decide** si consulta y **redacta** la Cypher él mismo vía tool use |
| System prompt: *"NO uses tools ni MCP"* | System prompt: **describe las dos tools** y cuándo usarlas; las 4 briefings pasan a ser **ejemplos de Cypher** en el prompt, no routing |
| Las aristas `:RESPONDE_EDGE` las crea el handler tras el stream (§2.6) | La escritura la hace el LLM vía **tool de escritura** (`:UserQuery` + `:RESULT_EDGE`), no código hardcodeado en el handler |
| `src/llm.py`: un único método `stream()` (§3.3) | `src/llm.py`: añade un **bucle controlador de tools** antes del stream final |

Lo que **no** cambia: estructura de `src/` (§4), preprocesado y carga a Neo4j (§2), generación de esquemas semánticos (§2.4), frontend `/chat` y `/graph` (§3.1, §3.4), `AsyncAnthropic` + streaming (§3.3), ventana deslizante de historial.

> **Nota de nomenclatura.** v3 §2.6 hablaba de `:QueryUsuario` / `:RESPONDE_EDGE`. La capa semántica ya implementada usa los nombres definitivos **`:UserQuery`** y **`:RESULT_EDGE`** (ver `ontology/semantic-layer/agents/`). v4 adopta esos.

---

## 2. Las dos tools

Decisión de diseño (justificada en la discusión previa): **tool use nativo de Anthropic, no parsing de tags `<>`.** El SDK entrega el `input` ya estructurado, el modelo se detiene con `stop_reason="tool_use"` a esperar el `tool_result`, y la alternancia `user/assistant/tool` la gestiona el protocolo. Parsear tags sobre el stream sería reinventar esto peor (el modelo puede alucinar el resultado, malformar el tag, etc.).

Son **dos tools con responsabilidad separada** — una lee, otra escribe. Nunca se mezclan: la de consulta es read-only de verdad (no puede mutar el grafo ni aunque el modelo lo intente), la de escritura solo crea `:UserQuery` + `:RESULT_EDGE`.

### 2.1 Tool de consulta — `consultar_grafo`

Read-only. El LLM redacta Cypher apoyándose en los esquemas y la ejecuta contra Neo4j.

```python
class ConsultarGrafoArgs(BaseModel):
    """Argumentos de la tool de consulta (validados antes de ejecutar)."""
    cypher: str = Field(description="Consulta Cypher de SOLO LECTURA.")
    motivo: str = Field(description="Qué sub-pregunta del usuario resuelve esta query.")
```

Tool definition (Anthropic):

```python
TOOL_CONSULTAR = {
    "name": "consultar_grafo",
    "description": (
        "Ejecuta una consulta Cypher de SOLO LECTURA sobre el grafo Neo4j de "
        "Reversa (12 285 normas del BOE y sus relaciones). Úsala siempre que "
        "necesites datos reales del grafo para responder. Para varias "
        "sub-preguntas, llámala varias veces (una por sub-pregunta)."
    ),
    "input_schema": ConsultarGrafoArgs.model_json_schema(),
}
```

Ejecución (read-only **a nivel de motor**, no solo de prompt):

```python
def _ejecutar_consulta(args: ConsultarGrafoArgs) -> list[dict]:
    _rechazar_si_escritura(args.cypher)          # allowlist: defensa en profundidad
    with driver.session(
        database=settings.neo4j.database,
        default_access_mode=neo4j.READ_ACCESS,   # el motor rechaza cualquier escritura
    ) as s:
        return [r.data() for r in s.run(args.cypher)]
```

### 2.2 Tool de escritura — `guardar_interaccion`

Crea **un** nodo `:UserQuery` y **N** aristas `:RESULT_EDGE` hacia las normas que el LLM ha usado para responder. El LLM la llama **una sola vez al final**, cuando ya tiene la respuesta y sabe qué normas la sustentan.

Argumentos alineados con los esquemas ya hechos (`agents/nodes/user_query.json`, `agents/edges/result_edge.json`):

```python
class ResultadoNorma(BaseModel):
    id_norma: str = Field(description="id BOE de la norma citada (e.g. BOE-A-2015-10565).")
    texto: str = Field(description="Qué resuelve, respecto a esa norma, la query que la trajo.")

class GuardarInteraccionArgs(BaseModel):
    """Crea el nodo :UserQuery y sus aristas :RESULT_EDGE."""
    user_prompt: str = Field(description="Pregunta original del usuario, literal.")
    bbdd_query: list[str] = Field(description="Las Cypher que ejecutaste para responder.")
    answer: str = Field(description="Respuesta en lenguaje natural devuelta al usuario.")
    resultados: list[ResultadoNorma] = Field(
        description="Normas que sustentan la respuesta; una arista :RESULT_EDGE por cada una."
    )
```

Tool definition:

```python
TOOL_GUARDAR = {
    "name": "guardar_interaccion",
    "description": (
        "Persiste la interacción en el grafo: crea el nodo :UserQuery con la "
        "pregunta, las Cypher usadas y la respuesta, y una arista :RESULT_EDGE "
        "hacia cada norma que sustenta la respuesta. Llámala UNA vez, al final, "
        "cuando ya tengas la respuesta definitiva."
    ),
    "input_schema": GuardarInteraccionArgs.model_json_schema(),
}
```

Ejecución (única sesión de escritura del flujo de chat; `id_nodo` lo genera el backend, no el LLM):

```python
def _guardar_interaccion(args: GuardarInteraccionArgs) -> dict:
    id_nodo = str(uuid7())
    with driver.session(database=settings.neo4j.database) as s:
        s.run(
            """
            CREATE (q:UserQuery {
              id_nodo: $id_nodo, user_id: $user_id, user_prompt: $user_prompt,
              bbdd_query: $bbdd_query, answer: $answer, ts: datetime()
            })
            """,
            id_nodo=id_nodo, user_id="unknown",
            user_prompt=args.user_prompt, bbdd_query=args.bbdd_query, answer=args.answer,
        )
        for r in args.resultados:
            s.run(
                """
                MATCH (q:UserQuery {id_nodo: $id_nodo})
                MATCH (n:Norma {id: $id_norma})
                MERGE (q)-[e:RESULT_EDGE]->(n)
                SET e.texto = $texto
                """,
                id_nodo=id_nodo, id_norma=r.id_norma, texto=r.texto,
            )
    return {"id_nodo": id_nodo, "aristas": len(args.resultados)}
```

> `MATCH (n:Norma {id})` (no `MERGE`) en el destino: solo se conecta a normas que **ya existen**. Si el LLM alucina un id inexistente, esa arista simplemente no se crea — no se ensucia el grafo con placeholders.

---

## 3. El bucle controlador (`src/llm.py`)

Tool use **es** un bucle controlador — la diferencia con los tags es que el SDK estructura y delimita los turnos por ti. El método de chat de `Llm` (§3.3 de v3) se amplía así:

```python
TOOLS = [TOOL_CONSULTAR, TOOL_GUARDAR]
_MAX_ITERS = 6   # tope anti-bucle-infinito

async def responder(self, user_text: str) -> AsyncIterator[str]:
    """Bucle de tools (sin stream) y respuesta final (con stream)."""
    self._push("user", user_text)
    for _ in range(_MAX_ITERS):
        resp = await self._client.messages.create(
            model=self.model, max_tokens=self.max_tokens, temperature=self.temperature,
            system=self.system_prompt, tools=TOOLS, messages=self.messages,
        )
        self.messages.append({"role": "assistant", "content": resp.content})
        if resp.stop_reason != "tool_use":
            break                                  # ya no quiere más tools → narrar
        results = []
        for blk in resp.content:
            if blk.type != "tool_use":
                continue
            out = self._despachar_tool(blk.name, blk.input)   # valida con Pydantic
            results.append({"type": "tool_result", "tool_use_id": blk.id,
                            "content": json.dumps(out, ensure_ascii=False)})
        self.messages.append({"role": "user", "content": results})

    # Respuesta final en streaming token a token (§3.3)
    async with self._client.messages.stream(
        model=self.model, max_tokens=self.max_tokens, temperature=self.temperature,
        system=self.system_prompt, tools=TOOLS, messages=self.messages,
    ) as s:
        async for token in s.text_stream:
            yield token
    # tras el stream, el assistant final ya incluye la llamada a guardar_interaccion
```

**Interacción con el streaming.** El streaming token-a-token es **solo para la prosa final** que ve el usuario. Las iteraciones intermedias (`tool_use` ↔ `tool_result`) son tráfico de control y **no se streamean** como texto. Encaja con `AsyncAnthropic` y la `/chat` de NiceGUI sin cambios en el frontend.

**Varias sub-preguntas → varias llamadas.** En una sola iteración el modelo puede emitir varios bloques `tool_use` (uno por sub-pregunta); el bucle los ejecuta todos y devuelve todos los `tool_result` en el mismo turno `user`. Si necesita encadenar (el resultado de una alimenta la siguiente), itera de nuevo. El tope `_MAX_ITERS` lo acota.

**Historial deslizante (§3.3).** Cuidado: ahora los turnos incluyen pares `tool_use`/`tool_result` que **no se pueden separar** al recortar la ventana, o la API falla. El recorte debe operar por **interacción completa** (user → [tools]* → assistant final), no por mensaje suelto.

---

## 4. Seguridad

Dejar que el LLM redacte Cypher es **input no confiable ejecutándose contra el grafo**. Aplica `security.md` en capas:

1. **Sesión/usuario read-only de verdad** para `consultar_grafo`: `default_access_mode=neo4j.READ_ACCESS` (mejor aún, un usuario Neo4j con rol de solo lectura). Un `DELETE`/`MERGE` generado por el modelo falla en el motor, no en una regex.
2. **Validación + allowlist** antes de ejecutar (`_rechazar_si_escritura`): rechazar si la query contiene `CREATE|MERGE|DELETE|SET|REMOVE|DROP|DETACH`. Defensa en profundidad sobre (1).
3. **Validación Pydantic** de todo `input` de tool antes de ejecutar (`*.model_validate(blk.input)`), como exige `security.md` para agentes.
4. La tool de escritura es la **única** vía de mutación del flujo de chat, y solo toca `:UserQuery` + `:RESULT_EDGE`. El `id_nodo` lo genera el backend (UUIDv7), nunca el LLM.
5. Nada de `eval`/`exec` ni f-strings con el texto del modelo fuera del driver; la Cypher se pasa tal cual al driver, que parametriza el resto.

---

## 5. Esquemas — ya hechos, la tool los consume

No se generan esquemas nuevos para esto. La tool y el system prompt referencian los existentes:

```
ontology/semantic-layer/
├── agents/                       ← JSON Schema (consumo máquina: tools, validación)
│   ├── nodes/
│   │   ├── norma.json            ← :Norma
│   │   └── user_query.json       ← :UserQuery  (id_nodo, user_id, user_prompt, bbdd_query[], answer)
│   └── edges/
│       ├── modifica.json
│       ├── deroga.json
│       ├── cita.json
│       └── result_edge.json      ← :RESULT_EDGE (texto)
└── humans/                       ← Markdown (consumo humano: revisión, PRs)
    ├── nodes/{norma.md, user_query.md}
    └── edges/{modifica.md, deroga.md, cita.md, result_edge.md}
```

- **`consultar_grafo`**: el system prompt incrusta (o resume) los esquemas de `agents/nodes/norma.json` y `agents/edges/*.json` para que el LLM sepa qué labels, propiedades y TYPEs existen al redactar Cypher.
- **`guardar_interaccion`**: sus `input_schema` derivan de `user_query.json` y `result_edge.json` — son el mismo contrato, así que nodo y arista escritos cumplen el esquema por construcción.

Estos esquemas siguen **regenerándose en cada preprocesado** (§2.4 de v3); la única novedad es que ahora **también** alimentan las tools del chat en runtime.

---

## 6. System prompt (reemplaza el esqueleto del §3.2 de v3)

```
Eres Reversa, un asistente jurídico especializado en el BOE. Tu única fuente de
verdad es el grafo Neo4j de Reversa (12 285 normas consolidadas y sus relaciones:
DEROGA, MODIFICA, CITA, AÑADE, SUSTITUYE, SUPRIME, DESARROLLA, APRUEBA, TRANSPONE,
EN_RELACION_CON).

Dispones de dos herramientas:
- consultar_grafo(cypher, motivo): ejecuta Cypher de SOLO LECTURA. Úsala siempre
  que necesites datos reales. Si la pregunta tiene varias sub-preguntas, llámala
  una vez por sub-pregunta.
- guardar_interaccion(user_prompt, bbdd_query, answer, resultados): al final,
  cuando ya tengas la respuesta, persiste la interacción y enlázala a las normas
  que la sustentan.

Esquema del grafo (labels y propiedades): <se incrusta aquí desde agents/*.json>.

Flujo: evalúa si necesitas consultar → consulta_grafo (las veces que haga falta)
→ redacta la respuesta citando normas en formato [BOE-A-YYYY-NNNNN — Título]
→ guardar_interaccion una sola vez.

NUNCA inventes ids ni títulos: solo cita normas devueltas por consultar_grafo.
Si el grafo no tiene la información, dilo. No ejecutes escrituras vía consultar_grafo.

Ejemplos de Cypher útiles (las 4 briefings del Consejo): <las 4 queries del §2.1 de v3>.
```

Las 4 briefings dejan de ser routing por regex y pasan a ser **ejemplos** que el modelo reutiliza o adapta.

---

## 7. Impacto en `src/` y config

- **`src/llm.py`**: añade `TOOLS`, `_despachar_tool`, el bucle de §3, y la conexión Neo4j read-only para `consultar_grafo`. La escritura puede vivir aquí o delegarse a un helper en `src/preprocess.py`/un módulo `src/graph.py` mínimo (reutilizando el driver). Mantener una sola clase `Llm` salvo que crezca demasiado.
- **`src/config.py`**: `LLMConfig` gana `max_tool_iters: int = 6`. `Neo4jConfig` sin cambios (la sesión read-only se pide por llamada, no necesita otra URI).
- **Tests** (`tests/test_preprocess.py` ya existe; añadir para el LLM, mockeando driver y cliente Anthropic — sin red, sin Neo4j real, según §2.7 de v3):
  - `test_consultar_grafo_rechaza_escritura` — `MERGE`/`DELETE` en la query → error antes de ejecutar.
  - `test_consultar_grafo_usa_sesion_read_only` — se abre la sesión con `READ_ACCESS`.
  - `test_bucle_para_en_stop_reason_no_tool_use` — sin `tool_use` → no itera más.
  - `test_varias_subpreguntas_varias_llamadas` — N bloques `tool_use` → N `tool_result` en el mismo turno.
  - `test_guardar_interaccion_crea_userquery_y_result_edges` — 1 `CREATE :UserQuery` + N `MERGE :RESULT_EDGE`; id de norma inexistente no crea arista.
  - `test_args_tool_validados_con_pydantic` — `input` malformado → rechazo.
```