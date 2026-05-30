# Plan: Aislar todos los esquemas en `src/schemas.py`

## 1. Contexto y problema

Hoy las definiciones de "qué es un nodo / qué es una arista" están **dispersas entre tres ficheros**:

| Fichero | Qué define | Forma |
|---|---|---|
| `src/preprocess.py` | `Norma` (dataclass de runtime), `Referencia` | `@dataclass` |
| `src/preprocess.py` | `NormaSchema`, `EdgeSchema` (esquemas JSON para docs/agents) | `BaseModel` |
| `src/preprocess.py` | `_NORMA_MD_FIELDS`, `_ANALISIS_MD_FIELDS`, `render_md_norma`, `render_md_edge` | tablas + renderers |
| `src/config.py` | `RelacionConfig.codigos_a_relacion` (qué aristas se materializan) | `BaseModel` |

Esto causa tres problemas:

1. **Cuando aparece un nuevo tipo de nodo** (p. ej. `UserQuery`) hay que tocar `preprocess.py`, que conceptualmente es un *driver de carga*, no la definición de la ontología.
2. **El campo `materias` o `titulo` está descrito en tres sitios** — el `@dataclass Norma`, el `BaseModel NormaSchema` y la tabla `_NORMA_MD_FIELDS`. Cambiar una descripción exige cambiar las tres.
3. La separación **semántica / cinética / dinámica** (vocabulario Palantir-style que ya usamos en `ontology/`) no se refleja en el código: no hay un sitio que diga "esto es el modelo semántico", "esto materializa, esto lo crea el LLM en runtime".

El objetivo es que `src/schemas.py` sea la **única fuente de verdad** de la ontología, y que `preprocess.py`, `api.py` y futuros módulos LLM consuman desde ahí.

---

## 2. Modelo conceptual (las tres capas)

Mantenemos el vocabulario Palantir (ya presente en `ontology/{semantic,kinetic,dynamic}-layer/`):

- **Capa semántica** — el *vocabulario*. Qué tipos de nodo y arista existen, con qué propiedades. Es estática y la define el desarrollador. Es lo que debe vivir en `schemas.py`.
- **Capa cinética** — la *materialización en Neo4j*. Cómo se cargan los nodos `:Norma` y las aristas `DEROGA/MODIFICA/CITA` desde el BOE. Vive en `preprocess.py` y consume `schemas.py`.
- **Capa dinámica** — lo que se **crea en runtime** por un LLM (consultas de usuario, respuestas). Tiene su propia definición en `schemas.py` pero NO se materializa por el preprocesado: se materializa por la pipeline LLM (a crear más tarde).

**Regla clave de diseño:** todos los esquemas (semánticos *y* dinámicos) se definen en el mismo sitio porque comparten forma — son nodos y aristas Neo4j. Lo que cambia es **quién los crea** (preprocesado vs LLM), no **qué son**.

---

## 3. Inventario de esquemas tras la migración

### 3.1 Nodos

**`Norma` (capa semántica)** — ya existe, se mueve sin cambios estructurales.
- Origen: parseo XML del BOE.
- Materialización: `Preprocesador._upsert_norma`.

**`UserQuery` (capa dinámica)** — nuevo.

| Campo | Tipo | Obligatorio | Default | Descripción |
|---|---|---|---|---|
| `id_nodo` | string | sí | — | Identificador único del nodo (p. ej. UUID v4). |
| `user_id` | string | no | `"unknown"` | Identificador del usuario. Default según requisito. |
| `user_prompt` | string | sí | — | Prompt en lenguaje natural enviado por el usuario. |
| `bbdd_query` | string | sí | — | Cypher generado por el LLM a partir del prompt. |
| `answer` | string | sí | — | Respuesta en lenguaje natural devuelta al usuario. |

Materialización: la pipeline LLM (`src/llm.py`, fuera del alcance de este plan) hará el `MERGE (q:UserQuery {id_nodo: $id})`.

### 3.2 Aristas

**Aristas semánticas** — generadas por preprocesado.
Las define `RelacionConfig.codigos_a_relacion` (queda en `config.py`, ver §5):
```
210 → DEROGA
270 → MODIFICA
330 → CITA
```
Comparten el mismo `EdgeSchema` actual (`relacion_codigo`, `relacion`, `texto`).

**Arista dinámica — `RESULT_EDGE`** — nueva, generada por el LLM.
Une `(:UserQuery) -[:RESULT_EDGE]-> (:Norma)`. Una `UserQuery` puede tener N `RESULT_EDGE` si la respuesta cita múltiples normas.

| Campo | Tipo | Descripción |
|---|---|---|
| `rank` | int | Posición de la norma en la respuesta (1 = primera citada). |
| `score` | float \| None | Relevancia opcional asignada por el LLM. |

> Justificación de campos: el requisito no especifica atributos; uso `rank` (orden de aparición, imprescindible para reconstruir la respuesta) y `score` opcional (típico en retrieval). Si prefieres un edge sin propiedades, basta con dejar un `BaseModel` vacío y ya está.

### 3.3 Tabla resumen final

| Esquema | Capa | Tipo | Creador |
|---|---|---|---|
| `Norma` | semántica | nodo | Preprocesado |
| `DEROGA`, `MODIFICA`, `CITA` | semántica | arista | Preprocesado |
| `UserQuery` | dinámica | nodo | LLM en runtime |
| `RESULT_EDGE` | dinámica | arista | LLM en runtime |

---

## 4. Estructura propuesta de `src/schemas.py`

```
src/schemas.py
├─ docstring de módulo: "Única fuente de verdad de la ontología."
│
├─ # ─── Modelos runtime (dataclasses usadas en parseo y materialización) ───
│  ├─ Referencia        (dataclass)
│  └─ Norma             (dataclass)   ← migrado desde preprocess.py
│
├─ # ─── Esquemas semánticos: nodos ───
│  └─ NormaSchema       (BaseModel)   ← migrado desde preprocess.py
│
├─ # ─── Esquemas semánticos: aristas ───
│  └─ EdgeSchema        (BaseModel)   ← migrado desde preprocess.py
│
├─ # ─── Esquemas dinámicos: nodos ───
│  └─ UserQuerySchema   (BaseModel)   ← NUEVO
│
├─ # ─── Esquemas dinámicos: aristas ───
│  └─ ResultEdgeSchema  (BaseModel)   ← NUEVO
│
└─ # ─── Renderers de documentación humana ───
   ├─ _NORMA_MD_FIELDS            ← migrado desde preprocess.py
   ├─ _ANALISIS_MD_FIELDS         ← migrado desde preprocess.py
   ├─ render_md_norma(flags)      ← migrado desde preprocess.py
   ├─ render_md_edge(rel_type, codigo)  ← migrado desde preprocess.py
   ├─ render_md_user_query()      ← NUEVO (sin flags, todo el contenido es fijo)
   └─ render_md_result_edge()     ← NUEVO
```

**Convenciones que sigue:**
- Todo lo del **mismo grupo conceptual** (semántico vs dinámico, nodo vs arista) queda contiguo.
- Los renderers viven aquí porque dependen 1:1 de los esquemas — separarlos volvería a fragmentar la ontología.
- `Norma` / `Referencia` siguen siendo `@dataclass` porque son objetos de runtime baratos, no esquemas de validación. `NormaSchema` sí es `BaseModel` porque su única razón de existir es producir el JSON Schema para los agentes.

---

## 5. Qué se queda fuera de `schemas.py` (y por qué)

- **`RelacionConfig`** sigue en `config.py`. Es **configuración** (qué códigos materializar de los ~50 del catálogo BOE), no esquema. El esquema de una arista es `EdgeSchema`; qué subconjunto de códigos se carga es decisión operativa.
- **`ParseFlags`, `MetadatosFlags`, `AnalisisFlags`** se quedan en `config.py`. Son flags que controlan **qué se extrae**, no la definición de qué es una `Norma`.
- **`Preprocesador`, `BOEDownloader`** se quedan donde están. Consumen los esquemas, no los definen.

Esta línea (esquema vs config) es la que evita que `schemas.py` se convierta en un cajón de sastre.

---

## 6. Cambios concretos por fichero

### `src/schemas.py` (nuevo)
- Crear el fichero con la estructura del §4.
- Mover `Referencia`, `Norma`, `NormaSchema`, `EdgeSchema`, `_NORMA_MD_FIELDS`, `_ANALISIS_MD_FIELDS`, `render_md_norma`, `render_md_edge` desde `preprocess.py`.
- Añadir `UserQuerySchema`, `ResultEdgeSchema`, `render_md_user_query`, `render_md_result_edge`.

### `src/preprocess.py`
- Eliminar las clases/funciones movidas.
- Importar desde `src.schemas`: `Norma`, `Referencia`, `NormaSchema`, `EdgeSchema`, `render_md_norma`, `render_md_edge`.
- `regenerar_esquemas_semanticos` se queda aquí (es lógica de I/O sobre `semantic-layer/`), pero ahora importa los renderers y modelos desde `schemas.py`.
- *Decisión abierta:* `regenerar_esquemas_semanticos` solo escribe nodos/aristas semánticos. Los esquemas dinámicos (`UserQuery`, `RESULT_EDGE`) **también deben tener su `.md` y `.json` en `semantic-layer/`** — son parte del vocabulario aunque los instancie el LLM. La función debe escribirlos también, pero sin depender de `flags` (la dinámica no tiene flags). Ver §7.

### `src/config.py`
- Sin cambios. `RelacionConfig` y los `*Flags` siguen donde están.

### `tests/test_preprocess.py`
- Cambiar imports: `from src.schemas import ...` para `parse_xml`-no (sigue en preprocess), pero sí para `render_md_*` y modelos.
- *Importante:* `parse_xml` se queda en `preprocess.py` (es lógica de extracción, no esquema). Solo los modelos/renderers se mueven.
- Añadir tests nuevos:
  - `test_user_query_schema_tiene_user_id_default_unknown`
  - `test_result_edge_schema_definido`
  - `test_regenerar_esquemas_incluye_user_query`
  - `test_regenerar_esquemas_incluye_result_edge`

### `ontology/kinetic-layer/` y `ontology/semantic-layer/`
- Tras la primera ejecución del preprocesado, `semantic-layer/humans/nodes/user_query.md` y `semantic-layer/agents/nodes/user_query.json` aparecerán automáticamente.
- Igual para `semantic-layer/{humans,agents}/edges/result_edge.{md,json}`.

---

## 7. Decisión: ¿cómo se escriben los esquemas dinámicos en `semantic-layer/`?

Dos opciones:

**Opción A — `regenerar_esquemas_semanticos` los escribe siempre.**
- Ventaja: un solo punto de generación, simétrico con `Norma` y las aristas semánticas.
- Justificación: aunque los nodos `UserQuery` los crea el LLM en runtime, *el contrato de qué campos tiene un `UserQuery`* es semántico y estático. El `semantic-layer/` documenta el contrato, no los datos.

**Opción B — Un comando separado `regenerar_esquemas_dinamicos`.**
- Ventaja: separa físicamente lo que el preprocesado materializa de lo que materializa el LLM.
- Desventaja: dos pipelines de docs, más complejo, dos sitios donde puedes olvidarte de regenerar.

**Recomendación: Opción A.** El `semantic-layer/` es la "tabla de tipos" del sistema, no un registro de qué se ha cargado. La capa dinámica se distingue por **dónde se crean los datos** (runtime LLM), no por dónde vive la definición del tipo.

---

## 8. Plan de ejecución (incremental, cada paso con verificación)

1. **Crear `src/schemas.py` con los modelos migrados** (Norma, Referencia, NormaSchema, EdgeSchema, renderers).
   - *Verificar:* `make test` sigue pasando con los imports apuntando a `src.schemas` desde `preprocess.py` y los tests.

2. **Añadir `UserQuerySchema` y `ResultEdgeSchema` con sus renderers.**
   - *Verificar:* tests unitarios nuevos `test_user_query_schema_*`.

3. **Integrar los dinámicos en `regenerar_esquemas_semanticos`.**
   - *Verificar:* tras correr `regenerar_esquemas_semanticos(base_dir=tmp_path)` existen los 4 ficheros nuevos (`user_query.md`, `user_query.json`, `result_edge.md`, `result_edge.json`).

4. **Limpieza:** asegurar que `preprocess.py` ya no define ninguna clase/función que también esté en `schemas.py`. Revisar imports.
   - *Verificar:* `make check` (ruff + mypy + pylint + complexipy) + `make test` con cobertura ≥ 80%.

---

## 9. Lo que NO se hace en este plan (alcance acotado)

- No se implementa la pipeline LLM que crea `UserQuery` / `RESULT_EDGE` en runtime. Solo el contrato de tipos.
- No se cambia la estructura de carpetas `ontology/` — ya está bien.
- No se refactorizan los `*Flags` ni `RelacionConfig` (ver §5).
- No se cambia el comportamiento de `Preprocesador` ni `BOEDownloader` más allá de los imports.

---

## 10. Preguntas abiertas antes de implementar

1. **`RESULT_EDGE` con propiedades o sin ellas?** Propongo `rank` + `score?`. Si quieres edges desnudos, dilo y dejo `ResultEdgeSchema` vacío.
2. **`UserQuerySchema` necesita `timestamp`?** No estaba en tu lista, pero típicamente es útil para auditoría. ¿Lo añado como opcional o lo dejo fuera?
3. **¿`semantic-layer/agents/nodes/user_query.json` debe llevar también el JSON Schema con `additionalProperties: false`?** Hace que el LLM no pueda inventarse campos. Recomendado.
