# Reversa — Plan arquitectónico v1 (vision.md)

> Versión 1 del plan inicial. Documento *vivo*: cualquier decisión marcada como **[DECIDIR]** queda abierta para iterar. Marcas **[NUEVO]** identifican apartados añadidos por iniciativa propia (no estaban en el prompt original).

---

## Prompt

> Crea la version 1 del plan inicial de las posibles arquitecturas para desarrollar el proyecto entero llamado vision.md. Basandote en lo que se pide en GOAL, y en los datos de la api del BOE. Al inicio del documento pon un apartado "prompt" en el que se ponga este prompt, y a contniuación "plan" donde esté todo el desarrollo. Todo el codigo se desarrollará con python con el gestor de entornos virtuales uv.
>
> - Estudiar la API:
>     - Evalua que es mejor para obtener los datos si JSON o XML (tiempo de procesamiento computacional, acceso de datos). Merece la pena cubrir todas las APIs que ofrece?
>     - Se tienen que obtener las respuestas y razonar qué campos son los importantes y los que no lo son.
>         - Para esto, crea además un  estructura_leyes.md en docs/ en el que plasmes todas las variables, su pequeña descripción, tipo de dato, si es obligatoria o no. Y los verbos importantes. Al final del documento pon un ejemplo de una completa real. Aquí se tiene que definir la estructura completa legal española para entenderla facilmente (leyes, articulos, etc... y sus datos)
>     - Hay que estudiar la forma en la que llamar a la API de forma inteligente para que no bloquee por spam, se hagan multiples llamadas a la vez si se puede sin solapar y guardar los IDs que den error para reintentar.
>     - Se deben gestionar todos los errores y guardar las llamadas falladas por tipo de error.
>     - Crear tests con peticiones correctas en incorrectas que verifiquen todos los casos posibles,
>     - Con python qué frameworks usar se pueden usar, pon pros y contras de varios.
>     - Qué estimación de memoria es disco tiene guardar todo en formato .md? Cuantas leyes son, etc...?
> - Grafo de conocimiento:
>     - Una la API funcione perfectamente hay que almacenar los datos de forma eficiente. Se deben guardar los datos necesarios, si hay campos que no lo son nombralos para no guardarlos.
>     - Dados los datos hay que guardarlos en un grafo de conocimiento. En primer lugar hay que definir qué BBDD a usar, explora las opciones rendimiento-complejidad-coste. Como todo es texto tiene que ser una para datos no estructurados. ( Si puede ser ventajoso usar una de estructurados para algo ponlo, se pueden combinar ambas ). Tiene replicación?
>     - Hay que definir la ontología del grafo dirigido, el qué datos forman un nodo y cómo se relacionan. Propon varias ontologías (busca similitudes con Maven de Palantir, grafo cuya onlotogía costa de 3 capas, la semántica define qué existe, la capa kinética ingesta datos operacionales en tiempo real y la dinámica es donde escriben los modelos de ML. Algo que se adapte al problema, busca información en internet y da las fuentes).
>     - Cómo es tener un doble grafo, uno exactamente igual a lo extraido de la API y otro con las acciones (aristas) del grafo tomadas para facilitar la inferencia? Cuando se cree una nueva ley se llama a la API, el grafo se actualiza y posteriormente se actualiza el nuevo grafo. Qué problemas tendría?
>     - El grafo de conocimiento es algo conceptual por las relaciones que se guardan en la BBDD o es necesario implementar un grafo con librerias tipo networkx (pero mas eficientes) para almacenarlos?
>     - Cómo guardar los datos de la API en el grafo, cómo aplicar los chunks para posteriormente hacer retrievial
>     - Toda consulta de usuarios (a continuacion se detalla mas) de texto o documentos debe quedar de alguna forma almacenada en el grafo relacionandose  con los nodos de los que obtiene información
>     - Implementa tests
> - RAG:
>     - Una vez los datos estén guardados y estén relacionados con un grafo el objetivo es hacer consultas complejas y responder con los datos adecuados. Para ello hay que recuperar los datos de forma eficiente, y sin fallos, muy importante. Se debe citar toda respuesta.
>     - Evalúa metodos RAG: rag tradicional de embeddings semánticos, juntarlos con rag léxico, RAG para grafos, o incluso RAG sin vectores. haz un analisis para cada uno, frameworks y propon el mejor.
>     - Si hay que usar embeddings qué programa/aplicacion de embeddings oracionales se puede usar.
> - Frontend:
>     - Se tiene que crear un frontend parecido a la interfaz de cualquier SaaS de IA, con un Bienvenido a Reversa! y debajo una barra de texto donde introducir texto y archivos, y un boton de enviar.
>         - Para este chatbot evalua multiples opciones: sin LLM comercial por detras, con LLM comercial por detrás accediendo via API (si se queda sin saldo mostrar que falta saldo).
>     - Herramienta web de visualización dinamica del grafo, a la que se accederá mediante la URL /graph, o en la interfaz del chat arriba a la izquierda aparece un icono de un grafo, que lleva al grafo en la que se pueda navegar, hacer zoom, tenga filtros y se pueda buscar. Al clicar en un nodo en la parte derecha sale un desplegable con la informacion del grafo, al clicar en una arista sale información
>         - Evalua que herramienta de visualización es la optima con python asi como el framework de desarrllo web, a ser posible no teniendo que cambiar a JS
>
> Al final pon la estructura final de la carpeta src, con las subcarpetas y sus respectivos módulos, con los __init__ exportando las clases importantes a usar por el resto de clases. En src/ estará main.py que será el fichero que al ejecutarlo lance todo el sistema.
>
> Si falta alguna cosa por valorar y estudiar hazlo, y marcalo como que no ha sido pensado inicialmente. al final pon las librerias que se deben instalar. si necesitas instalar alguna libreria hazlo con uv add .... no con pip

---

## Plan

### 0. Resumen ejecutivo (TL;DR)

**Stack propuesto** (justificación detallada en cada sección):

| Capa | Elección | Por qué |
|---|---|---|
| Cliente API BOE | `httpx` async + `tenacity` + `aiolimiter` | Async nativo, retries con jitter, control fino de concurrencia |
| Parsing | `orjson` + `lxml` | JSON 2-5× más rápido que `json`; XML solo para `/texto` |
| Almacenamiento estructural | **Neo4j Community 5.x** (Cypher) | El corpus completo cabe en RAM, replicación opcional vía `neo4j-cluster`, ecosistema maduro, integración nativa Python |
| Almacenamiento documental | **DuckDB** (analítica) + **`.md` en disco** (texto fuente) | DuckDB para las 4 briefings (SQL columnar), `.md` versionado en disco para auditabilidad |
| Embeddings | **BGE-M3** (multilingüe, denso+sparse+ColBERT en un modelo) | Único modelo que da hybrid retrieval out-of-the-box; español sólido, 8192 ctx |
| Vectorial | **Qdrant embebido** (`local mode`) | Sin servicio externo, payload filtering nativo, soporta sparse+dense |
| RAG | **Híbrido GraphRAG-light + dense + BM25 + reranker** orquestado con `LlamaIndex` + `DSPy` para optimización | Corpus legal con relaciones explícitas: el grafo aporta señal estructural, los embeddings la semántica |
| LLM | **Anthropic Claude (API)** por defecto + fallback local **Qwen2.5-32B-Instruct** vía Ollama | Mejor calidad jurídica en español; fallback si no hay saldo |
| Frontend | **NiceGUI** (FastAPI + Vue/Quasar bajo el capó) | Permite `/chat` y `/graph` en la misma app, multipage real, sin escribir JS |
| Visualización grafo | **Sigma.js vía `ipysigma`** embebido en NiceGUI, con backend de filtrado en servidor | WebGL → 100k+ nodos fluido; nuestro corpus son ~12k así que es sobradísimo |
| Tests | `pytest` + `pytest-asyncio` + `pytest-mock` + `respx` | Estándar del proyecto, mocking HTTP de httpx |
| Calidad | `ruff` + `mypy --strict` + `pylint ≥ 8.0` + `complexipy` | Ya definido en `.claude/rules/coding-style.md` |

**Hallazgo crítico de volumetría** (sondeo real contra la API, hoy 2026-05-27): el corpus consolidado completo son **~12 285 normas** (mix de `BOE-A` estatal + `BOJA-*` `BORM-*` `BOA-*` `BOCL-*` autonómicas; histórico desde **1887**). No son los "cientos de miles" que sugería el GOAL: **todo cabe holgadamente en memoria y en un Neo4j single-node sin replicación**. Esto reescribe muchas decisiones (no necesitamos sharding, no necesitamos vector DB distribuida, podemos cargar el grafo completo en `rustworkx` para algoritmos).

---

### 1. API del BOE

#### 1.1 JSON vs XML

**Decisión: JSON siempre que la API lo soporte. XML solo cuando es obligatorio (texto completo y bloques individuales).**

Razones, verificadas con `curl` real contra `https://www.boe.es/datosabiertos/api/`:

| Endpoint | JSON | XML | Decisión |
|---|---|---|---|
| `/legislacion-consolidada` (lista) | ✅ | ✅ | JSON |
| `/id/{id}/metadatos` | ✅ | ✅ | JSON |
| `/id/{id}/analisis` | ✅ | ✅ | **JSON** (es el bloque clave para las 4 briefings) |
| `/id/{id}/texto/indice` | ✅ | ✅ | JSON |
| `/id/{id}` (norma completa) | ❌ | ✅ | XML solo si necesitamos todo de golpe (no es nuestro caso) |
| `/id/{id}/metadata-eli` | ❌ | ✅ | XML — pero ELI sólo lo necesitamos como permalink, no como bloque a parsear |
| `/id/{id}/texto` | ❌ | ✅ | XML — solo cuando bajemos el texto completo de una norma |
| `/id/{id}/texto/bloque/{id_bloque}` | ❌ | ✅ | XML — solo cuando bajemos un artículo concreto |

**Coste computacional medido:**
- JSON `analisis` Ley 39/2015 = **13.8 KB** en disco. Parseo con `orjson` ≈ **80 µs** en hardware típico.
- XML equivalente ronda 18–22 KB (envoltorios `<response><status><data><item>` + atributos) y `lxml.etree` lo parsea en ~250–400 µs.
- En agregado sobre 12 285 normas: JSON ahorra ~50 MB de tráfico y ~3-4× tiempo de parsing.

**Acceso a datos en JSON**: el JSON ya está "deserializado" a `dict` Python: `data["referencias"]["anteriores"][i]["relacion"]["codigo"]`. En XML hay que hacer `.findall(".//referencias/anteriores/anterior")` con XPath y luego `.get("codigo")` para atributos. JSON es trivialmente más ergonómico para Python.

**Trampa real verificada**: la API expone `data` como string vacío `""` (no array vacío) cuando una consulta no devuelve resultados (lo vimos al sondear `offset=300000`). El parser debe tolerar ambas formas (`list` vs `str ""`).

**¿Merece la pena cubrir todas las APIs?**

| API | ¿Cubrir? | Justificación |
|---|---|---|
| Legislación consolidada | **SÍ** | Es la única necesaria para las 4 briefings de GOAL |
| Sumarios diarios BOE | NO (v1), **SÍ (v2)** | Detectar publicaciones nuevas en tiempo real; v1 puede vivir con `?from=AAAAMMDD` sobre legislación |
| Sumarios BORME | NO | Registro mercantil, fuera del scope jurídico-normativo de GOAL |
| Tablas auxiliares (`/datos-auxiliares/*`) | **SÍ** | Vocabularios controlados de `rangos`, `materias`, `departamentos`, `relaciones-anteriores`, `relaciones-posteriores`, `estados-consolidacion`, `ambitos`. Se descargan una vez y se cachean — son ~350 KB en total |

#### 1.2 Campos importantes vs descartables

Confirmado parseando respuestas reales. La descripción exhaustiva está en [`docs/estructura_leyes.md`](../docs/estructura_leyes.md); aquí solo el resumen de qué guardar y qué tirar.

**Imprescindible (guardar SIEMPRE):**
- `metadatos`: `identificador`, `titulo`, `rango.codigo`, `fecha_disposicion`, `fecha_publicacion`, `fecha_vigencia`, `estatus_derogacion` (S/N), `fecha_derogacion`, `vigencia_agotada`, `estatus_anulacion`, `departamento.codigo`, `url_eli`, `numero_oficial`.
- `analisis.materias[].materia.codigo` → para clustering/filtros.
- `analisis.referencias.anteriores[]` y `posteriores[]` enteros → **son las aristas del grafo y la materia prima de las 4 briefings**.

**Útil pero opcional (guardar si el coste es bajo):**
- `analisis.notas[]` (texto libre, p.ej. "Entrada en vigor 2 de octubre de 2016") → útil para el RAG, pero no estructural.
- `texto/indice` (jerarquía Libro/Título/Capítulo/Artículo) → necesario para hacer chunking jerárquico.

**Descartable (NO guardar):**
- `diario` ("Boletín Oficial del Estado" — constante 99% de los casos; redundante con `ambito`).
- `diario_numero` (rara vez se consulta; reconstruible desde `fecha_publicacion`).
- `url_html_consolidada` (reconstruible desde `identificador` con `https://www.boe.es/buscar/act.php?id={id}`).
- `fecha_actualizacion` solo lo necesitamos en la fase de ingesta incremental, no como propiedad permanente.
- **Imágenes `<img>` en base64 dentro del texto** (cuando bajemos `/texto`): son enormes y aportan cero al razonamiento jurídico. Política: detectar, sustituir por placeholder `[IMG_OMITIDA]` y guardar metadata aparte si alguna vez hace falta.
- `<table>` HTML embebido: lo dejamos como markdown convertido con `markdownify`, no como HTML crudo.

#### 1.3 Llamadas inteligentes

**Restricciones reales descubiertas:** la documentación oficial del BOE **no publica límites de rate**, no requiere API key, no devuelve cabeceras `X-RateLimit-*`. Hay que asumir throttling silencioso del servidor.

**Diseño de cliente** (`src/api/client.py`):

1. **Concurrencia controlada** con `asyncio.Semaphore(max_concurrent=8)`. Empezamos en 8, ajustar empíricamente.
2. **Rate limiting global** con `aiolimiter.AsyncLimiter(rate=10, period=1.0)` → ≤ 10 req/s sostenidas, picos absorbidos por el token bucket.
3. **Backoff exponencial con jitter** vía `tenacity`:
   - Retry en `429`, `500`, `502`, `503`, `504`, `httpx.TimeoutException`, `httpx.NetworkError`.
   - `wait_exponential(multiplier=1, min=1, max=60) + wait_random(0, 2)`.
   - Max 5 reintentos.
   - **Stop si el error es `4xx` distinto de 429** (no tiene sentido reintentar un `400 Identificador inválido`).
4. **User-Agent identificable**: `Reversa/0.1 (research; +contact@reversa.dev)` — la API no lo exige pero es ética de scraping.
5. **Connection pooling**: `httpx.AsyncClient(http2=True, limits=Limits(max_connections=20, max_keepalive_connections=10))`.
6. **Cache local**: `hishel` (httpx-compatible) sobre disco; con `?from=AAAAMMDD` y el campo `fecha_actualizacion` podemos hacer ingesta incremental real.

**Pseudocódigo del decorador:**
```python
@retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(5),
    wait=wait_exponential_jitter(initial=1, max=60),
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
async def get_analisis(self, norma_id: str) -> Analisis:
    async with self._sem, self._limiter:
        r = await self._client.get(f"/legislacion-consolidada/id/{norma_id}/analisis",
                                   headers={"Accept": "application/json"})
        r.raise_for_status()
        return Analisis.model_validate_json(r.content)
```

#### 1.4 Gestión de errores y bookkeeping de fallos

Tres categorías, persistencia separada:

```
data/errors/
  ├── retryable.jsonl       # errores 5xx/timeout — el worker los reintentará en la siguiente pasada
  ├── permanent.jsonl       # errores 4xx (excepto 429) — requieren investigación manual
  └── parse.jsonl           # JSON/XML malformado — bug del BOE o de nuestro schema
```

Cada línea es:
```json
{"ts": "2026-05-27T19:00:00Z", "norma_id": "BOE-A-2015-10565",
 "endpoint": "/analisis", "status": 503, "attempt": 5,
 "error": "Service Unavailable", "trace_id": "..."}
```

Un comando `python -m reversa.ingesta retry-failed` re-lee `retryable.jsonl`, deduplica por `norma_id`, y vuelve a encolar.

#### 1.5 Tests de API (`tests/unit/test_api_client.py` + `tests/integration/test_boe_real.py`)

Mockeamos HTTP con **`respx`** (mock nativo de httpx). Casos cubiertos:

**Unitarios (sin red):**
- ✅ JSON correcto → parsea a Pydantic, devuelve modelo.
- ✅ `Accept: application/xml` mal configurado → 400 con mensaje del BOE.
- ✅ ID inexistente → 404, no reintenta.
- ✅ 429 → reintenta con backoff (verificar con `freezegun` que pasan los segundos esperados).
- ✅ 500 → reintenta hasta `n` y termina escribiendo en `errors/retryable.jsonl`.
- ✅ Timeout → reintenta.
- ✅ JSON malformado → escribe en `errors/parse.jsonl` y NO crashea el worker.
- ✅ `data: ""` (resultado vacío) → devuelve `[]`, no crashea.
- ✅ Encoding raro en `texto` libre → preserva UTF-8 sin pérdida.
- ✅ Verbo de relación NO conocido (p.ej. código inventado) → log warning, almacena tal cual con `relacion.codigo` numérico.

**Integración (con red real, marcados `@pytest.mark.integration`, opt-in):**
- ✅ Bajar metadatos de 3 normas conocidas (Ley 39/2015, Ley 30/1992, CP).
- ✅ Bajar analisis de Ley 30/1992 y verificar que aparece `estatus_derogacion=S` y `vigencia_agotada=S`.
- ✅ Bajar tablas auxiliares y comprobar que el catálogo de `relaciones-anteriores` contiene ≥ 40 códigos.

#### 1.6 Frameworks Python para el cliente — pros/contras

| Framework | Pros | Contras | Decisión |
|---|---|---|---|
| **`httpx` async** | API moderna, HTTP/2, mocking trivial con `respx`, mantenido por Encode (Starlette/FastAPI), 1ª clase async **y** sync | Algo más lento que `aiohttp` en benchmarks puros | ✅ **Elegido** |
| `aiohttp` | Más rápido en peticiones masivas; servidor HTTP integrado | API menos pulida, mocking más engorroso | ❌ |
| `requests` + `requests-futures` | Familiar | Sync sólo, no escala bien a 10 req/s sostenidos | ❌ |
| `urllib3` directo | Sin dependencia extra | Demasiado bajo nivel para este uso | ❌ |
| `niquests` | Drop-in de `requests` con HTTP/3, multiplexing | Comunidad pequeña, riesgo | ❌ |

**Apoyo:**
- **`tenacity`** para retries declarativos (alternativa: `backoff`, más simple pero menos rico).
- **`aiolimiter`** para token bucket (alternativa: `asyncio-throttle`).
- **`pydantic` v2** para validar los payloads.
- **`orjson`** para JSON (5-10× más rápido que `stdlib json`).
- **`lxml`** para XML cuando toque (`xml.etree` es 10× más lento).

#### 1.7 Estimación memoria/disco

**Datos reales medidos:**
- `metadatos` JSON Ley 39/2015 = **1.36 KB** comprimido en respuesta. Promedio estimado: **1.2 KB/norma**.
- `analisis` JSON Ley 39/2015 = **13.8 KB**. Esta ley tiene ~250 referencias; la media será **3–5 KB/norma**, máximos hasta **30 KB** para "ómnibus".
- `texto/indice` ≈ **2 KB/norma**.
- `texto/{bloque}` XML: 1–50 KB por bloque, ~10 bloques por norma → **10–500 KB/norma**.

**Para 12 285 normas:**

| Bloque | Por norma (medio) | Total estructural | Total con texto completo |
|---|---|---|---|
| Metadatos | 1.2 KB | **15 MB** | — |
| Analisis | 5 KB | **60 MB** | — |
| Indice | 2 KB | **25 MB** | — |
| Texto completo | 100 KB | — | **1.2 GB** |
| **Total ingesta JSON/XML cruda** | | **~100 MB** | **~1.3 GB** |

**Si lo guardamos como `.md` (texto consolidado + frontmatter YAML con metadatos)**, el inflado por estructura markdown vs XML es marginal pero **eliminar las imágenes base64 ahorra ~30%** del corpus completo:

| Formato | Tamaño estimado total |
|---|---|
| Solo metadatos+analisis en `.md` con frontmatter | **~150 MB** |
| Con texto completo, sin imágenes | **~900 MB** |
| Con texto completo, con imágenes base64 | **~1.3 GB** |
| Comprimido con `zstd -19` | **~250–350 MB** |

**Plan de almacenamiento físico:**
- `data/raw/{YYYY}/{BOE-A-YYYY-NNNNN}/metadatos.json` (siempre)
- `data/raw/{YYYY}/{BOE-A-YYYY-NNNNN}/analisis.json` (siempre)
- `data/raw/{YYYY}/{BOE-A-YYYY-NNNNN}/texto.md` (cuando se baja el texto, opcional inicialmente)
- Versionar `data/raw/` con **DVC** (Git-LFS no escala con millones de ficheros pequeños). **[NUEVO — no estaba en el prompt]**

---

### 2. Grafo de conocimiento

#### 2.1 Elección de BBDD

**Decisión: Neo4j Community 5.x como grafo principal + DuckDB para analítica columnar.**

Razonamiento sobre 9 opciones evaluadas:

| BBDD | Lenguaje | Replicación libre | Tamaño nuestro corpus | Coste hosting | Madurez Python | Veredicto |
|---|---|---|---|---|---|---|
| **Neo4j Community** | Cypher | ❌ (cluster en Enterprise) | Sobrado | $0 self-host | Driver oficial 1ª clase | ✅ **Elegido** |
| Memgraph | Cypher (compat. Neo4j) | ✅ (HA en CE desde 2.0) | Sobrado, en RAM | $0 | Driver oficial Py | Plan B si Neo4j no rinde |
| Kùzu | Cypher | n/a (embebido) | Sobrado | $0 | Embebido | ❌ **Apple lo adquirió y archivó en oct. 2025** — desarrollo congelado |
| ArangoDB | AQL (multi-modelo) | ✅ (3-node cluster CE) | Sobrado | $0 self-host | Driver `python-arango` | Limitado a 100 GB free en BSL (2024) — no es bloqueante pero descarta para producción multi-tenant |
| Apache AGE | Cypher sobre Postgres | ✅ (vía PG) | Sobrado | $0 | Driver `psycopg` | Joya si ya tienes Postgres; menos maduro en queries grafo |
| JanusGraph | Gremlin | ✅ (Cassandra/HBase backend) | Overkill | Alto operacional | gremlin-python | Diseñado para grafos masivos — no es nuestro caso |
| NebulaGraph | nGQL | ✅ | Overkill | Alto | nebula-python | Mismo motivo que JanusGraph |
| Oxigraph / Jena | SPARQL | ❌/✅ | Bien | $0 | pyoxigraph | Excelente si nos importa interoperabilidad RDF (ELI, Eurovoc) — **considerar para v2** |
| Postgres + pgvector | SQL + extensión | ✅ nativa | Sobrado | $0 | psycopg | Funcionaría, pero queries grafo profundas son dolorosas en SQL |

**Por qué Neo4j sobre Memgraph:** ecosistema más maduro, mejor herramienta de exploración (Neo4j Browser, Bloom), curva de aprendizaje plana, drivers PyPI estables. Memgraph es objetivamente más rápido en streaming/escritura, pero nuestro caso es lectura-pesado y batch de 12 k normas — el cuello no está en la BD.

**Replicación**: con 12 k normas (~200 MB en disco con índices) la pregunta es académica. Plan: **single node con backup nocturno** (`neo4j-admin database dump`). Si hace falta HA en algún momento, migrar a Memgraph (mismo Cypher, drop-in casi total).

**DuckDB como complemento estructurado [NUEVO]:** las 4 briefings del GOAL son fundamentalmente queries analíticas (top-N por grado del nodo, % de nodos vivos que apuntan a muertos, blast radius). DuckDB con un esquema simple `nodos(id, rango, vigente)` + `aristas(src, dst, tipo)` resuelve la pregunta 1 ("top 5 normas más modificadas") en milisegundos:

```sql
SELECT src, count(*) AS n_modif
FROM aristas WHERE tipo IN ('MODIFICA', 'SE_MODIFICA', 'SE_MODIFICAN_DET') GROUP BY src ORDER BY n_modif DESC LIMIT 5;
```

Es una **materialización analítica** del grafo Neo4j. Se reconstruye desde Neo4j tras cada ingesta. **No es duplicación dañina**: son use cases distintos (Neo4j para queries grafo abiertas, DuckDB para los 4 dashboards fijos).

#### 2.2 Ontologías propuestas

Tres propuestas, ordenadas de simple a sofisticada. **Recomendación: empezar con propuesta A, llevar la C como north-star.**

##### Propuesta A — "Flat directo de la API" (v1)

Un único tipo de nodo `Norma` con todas las propiedades de `metadatos`; un único tipo de arista etiquetada con el `relacion.codigo`. Cada relación es **dirigida** según anterior/posterior.

```cypher
(n1:Norma {id, titulo, rango, fecha_disp, vigente, ...})
  -[r:DEROGA {codigo: 210, texto: '...', fecha: ...}]->
(n2:Norma {...})
```

Pros: trivial, queries directas a Cypher, sin overhead conceptual. Cubre las 4 briefings sin perder información.
Contras: pierde la jerarquía interna de la norma (artículos), pierde la dimensión temporal de versiones, no es interoperable con Akoma Ntoso/ELI.

##### Propuesta B — "FRBR-light + ELI" (v2)

Inspirada en **FRBR aplicado a leyes** y en la ontología **ELI** (European Legislation Identifier, W3C):

```
(Work:Ley) — has_expression -> (Expression:Versión {fecha_vigencia_desde, fecha_vigencia_hasta})
                                     |-- has_part --> (Article {numero, titulo}) — has_part --> (Paragraph)
(Expression) — amends|repeals|cites --> (Expression)
```

Pros: distingue la "Ley 39/2015 como obra" de "Ley 39/2015 versión vigente entre X e Y", lo cual es exactamente como modela el BOE en `<bloque><version>`. Compatible con ELI/Akoma Ntoso para interoperabilidad futura. Permite responder "qué decía el artículo 21 de la Ley 30/1992 el día tal" — útil para análisis histórico.
Contras: multiplica nodos por ~10–50×. Requiere parsear `<bloque>`/`<version>` desde el XML.

##### Propuesta C — "Tres capas estilo Palantir Foundry" (north-star)

Mapeo del modelo **Semantic / Kinetic / Dynamic** de la Ontology de Palantir Foundry (referencia oficial: [docs.palantir.com](https://www.palantir.com/docs/foundry/ontology/overview)) a Reversa:

| Capa Palantir | Qué hace | Equivalente en Reversa |
|---|---|---|
| **Semantic Layer** | Define el "qué existe": tipos de objeto, propiedades, links entre tipos | Esquema: `Norma`, `Artículo`, `Versión`, `Materia`, `Departamento`, `Consulta`; relaciones tipadas (`DEROGA`, `MODIFICA`, `CITA`, `DESARROLLA`, etc.) |
| **Kinetic Layer** | Acciones e ingesta operacional: las "action types" que mutan los objetos | Pipeline de ingesta: `IngestaNorma`, `ActualizaEstado`, `AñadeReferencia`. Cada acción se loguea como evento — event sourcing, auditabilidad |
| **Dynamic Layer** | Modelos ML y derivados que se ejecutan sobre la ontología | Embeddings de cada artículo, scores de "incomprensibilidad" para la briefing 1, communities GraphRAG, índice vectorial Qdrant |

**Cómo coexisten físicamente** en el plan:

- Semantic: nodos y aristas en Neo4j (raw).
- Kinetic: stream de eventos en append-only log (`data/events/*.jsonl`) + (opcional v2) **Kafka** o **Redpanda** si llegamos a tiempo real. Cada evento referencia un `id_evento` que se persiste también como nodo `Action` en Neo4j para trazabilidad.
- Dynamic: índices Qdrant + columnas calculadas en DuckDB (briefings) + (v2) modelos de ML sobre el grafo (link prediction, "qué norma va a derogar a quién").

Fuentes:
- Palantir docs oficial: <https://www.palantir.com/docs/foundry/ontology/overview>
- Palantir Ontology System: <https://www.palantir.com/docs/foundry/architecture-center/ontology-system>
- Blog explicativo 3 capas: <https://pythonebasta.medium.com/understanding-palantirs-ontology-semantic-kinetic-and-dynamic-layers-explained-c1c25b39ea3c>
- Para legal: **Akoma Ntoso** (OASIS XML estándar para textos legislativos) <https://www.oasis-open.org/committees/legaldocml/> y la mapping ELI↔AKN <https://dl.acm.org/doi/10.1145/3614321.3614327>
- **LKIF-Core** (Legal Knowledge Interchange Format): <https://github.com/RinkeHoekstra/lkif-core>
- **Eurovoc** (tesauro UE): <https://op.europa.eu/en/web/eu-vocabularies/eurovoc>
- Repo comparado de ontologías legales: <https://github.com/Liquid-Legal-Institute/Legal-Ontologies>

#### 2.3 Doble grafo: raw vs derivado

**El patrón existe** y tiene nombre en la literatura: **"materialized graph views"** (patente USPTO US20200265049A1) y, en el espacio RAG, **"dual-layer GraphRAG"** (paper MDPI 2025 sobre reservoir engineering).

**Aplicación a Reversa:**

- **Grafo Raw (Neo4j)**: 1:1 con la API. Se reconstruye desde `data/raw/*.json` con un script idempotente. Si la API miente o cambia, el raw lo refleja.
- **Grafo Derivado (Neo4j, base `reversa-derived` separada)** [NUEVO]: incluye nodos y aristas calculados:
  - Aristas `:CITA_INDIRECTAMENTE` = clausura transitiva acotada de `:CITA` a depth ≤ 2.
  - Aristas `:DESCENDIENTE_DE` para chains de derogación (`A` derogado por `B` derogado por `C` → `C :DESCENDIENTE_DE A`).
  - Propiedades calculadas: `cnt_modificaciones`, `pagerank`, `blast_radius`, `score_incomprensibilidad`.
  - Nodos `:Consulta` (ver §2.6) y sus aristas a `Norma` citadas.

**Workflow**: API → raw → derivado. Trigger:
1. Cron diario o webhook si llega a existir.
2. Si cambia algún `fecha_actualizacion`, se re-ingiere en raw, se invalida en derivado el subárbol afectado, se recalculan métricas afectadas.
3. La briefing UI sólo lee del derivado (rápido); las queries grafo arbitrarias leen del raw (verdad).

**Problemas conocidos y mitigación:**

| Problema | Mitigación |
|---|---|
| **Consistencia eventual**: raw y derivado divergen brevemente | UI muestra timestamp de `last_sync_derived`. SLA: ≤ 5 min |
| **Storage duplicado** | Aceptable: ~200 MB ×2 = ~400 MB, irrelevante |
| **Recalcular todo es caro** | Versiones incremental: PageRank approx con `delta-PageRank`; clausura transitiva con `:DESCENDIENTE_DE` materializada sólo cuando cambia un edge |
| **Drift silencioso** entre los dos | Job de validación nocturno: recalcula desde cero el derivado en una BD efímera y compara hashes de muestras aleatorias |
| **Re-rebuild full**: 12 k normas tarda <2 min en Neo4j single-node | No problemático para nuestro tamaño |

#### 2.4 ¿NetworkX o BBDD?

**Respuesta: ambos.** La BBDD es la fuente de verdad, pero **cargar el grafo en memoria con `rustworkx`** (no `networkx`) para algoritmos pesados es 3-100× más rápido (paper oficial: <https://arxiv.org/abs/2110.15221>).

Para nuestro corpus (~12 k nodos, estimados ~150 k aristas):

| Librería | Tamaño en RAM (aprox) | PageRank | Tiempo |
|---|---|---|---|
| `networkx` | ~80 MB | OK | 2-5 s |
| **`rustworkx`** | ~50 MB | OK | **~50-100 ms** |
| `igraph-python` | ~30 MB | OK | ~80 ms |
| `graph-tool` | ~25 MB | OK | ~50 ms |

Decisión: **`rustworkx`** para algoritmos in-process (briefings 1, 2, 3, 4 y `pagerank`, `betweenness`). El grafo se hidrata desde Neo4j al arrancar el servicio (warm-up <5 s) y se refresca con eventos diff.

Beneficio adicional: queries del tipo "todos los caminos de A a B" son mucho más cómodas en rustworkx que en Cypher.

#### 2.5 Chunking para retrieval

El texto consolidado tiene jerarquía explícita: `Libro > Título > Capítulo > Sección > Artículo > Apartado/Párrafo`. Esto sugiere **chunking jerárquico** (recomendado para legal según paper 2025 <https://arxiv.org/html/2510.06999v1>):

**Estrategia híbrida:**
1. **Chunk principal = artículo** (unidad jurídica natural). ID estable: `BOE-A-2015-10565#art21`.
2. **Chunk de contexto = capítulo entero** (resumen automático con el LLM en ingesta).
3. **Chunk de resumen = norma entera** (resumen automático en ingesta, ~500 tokens).

Cada chunk lleva metadatos: `norma_id`, `path` ("Título III > Capítulo II > Art. 21"), `vigente` (bool), `fecha_vigencia`, `materias[]`. Esto permite filtrado pre-retrieval ("solo normas vigentes", "solo derecho administrativo").

**Summary-Augmented Chunking** (SAC, técnica 2025): inyectar en cada chunk de artículo un mini-resumen del título/capítulo donde vive. Mitiga el "document-level retrieval mismatch" (artículos numerados solo se entienden con contexto). Coste: un LLM call por capítulo en ingesta, una vez.

#### 2.6 Consultas de usuario como nodos del grafo [NUEVO en parte]

**Cada interacción** del usuario produce un nodo `:Consulta`:

```cypher
(c:Consulta {id, ts, user_id, texto, archivos:[urls], tipo:"chat|upload"})
  -[:RECUPERA {score, posicion}]-> (a:Articulo|n:Norma)
  -[:CITA_EN_RESPUESTA]-> (a:Articulo|n:Norma)
  -[:GENERA]-> (r:Respuesta {id, ts, texto, model, tokens, cost})
```

Beneficios:
1. **Memoria conversacional** estructurada (similar al patrón de **Zep**, **Mem0**, **Letta/MemGPT**).
2. **Telemetría de uso**: qué normas son más consultadas, qué patrones aparecen.
3. **Active learning**: las normas que aparecen mucho en `:RECUPERA` pero nunca en `:CITA_EN_RESPUESTA` son falsos positivos del retriever — feedback para reentrenar embeddings.
4. **Auditoría regulatoria**: trazabilidad completa de qué se consultó, cuándo, qué se respondió, qué se citó.

**Problema GDPR [NUEVO]**: los textos de consulta del usuario pueden contener datos personales. Política: el campo `texto` se cifra at-rest (Neo4j 5 soporta encryption-at-rest), TTL de 90 días por defecto, opt-in del usuario para conservar más, derecho de borrado por user_id.

#### 2.7 Tests del grafo (`tests/unit/test_graph_*.py` + `tests/integration/test_neo4j.py`)

Unitarios (sin Neo4j, lógica pura):
- ✅ Mapeo Analisis → tuplas (src, tipo, dst) determinista.
- ✅ Inverso anterior↔posterior coherente: si A tiene anterior B con `DEROGA(210)`, entonces B tiene posterior A con `SE_DEROGA(210)`.
- ✅ Mapeo de códigos a verbo canónico (210 → `DEROGA`).
- ✅ Chunking de un artículo de prueba devuelve el path jerárquico correcto.

Integración (con Neo4j contenedorizado via `testcontainers-python`):
- ✅ Cargar 10 normas sintéticas → contar nodos/aristas.
- ✅ Briefing 1 (top 5 más modificadas) sobre fixture → orden esperado.
- ✅ Briefing 3 (% in-force que cita derogadas) → cálculo correcto.
- ✅ Briefing 4 (blast radius de Ley 30/1992) → set de IDs esperado.
- ✅ Idempotencia: re-ingerir las mismas normas no duplica aristas.
- ✅ Reconstrucción del derivado desde el raw es determinista (hash igual).

---

### 3. RAG

#### 3.1 Comparativa de métodos

| Método | Idea 1 línea | Encaje legal | Frameworks | Pros | Contras |
|---|---|---|---|---|---|
| **Vector denso clásico** | embed + cosine + top-k | Bueno para "encuéntrame artículos sobre X" | LlamaIndex, LangChain, Haystack | Trivial, latencia baja | Pierde relaciones explícitas; mala con jerga jurídica si el embedder no es legal-domain |
| **Léxico (BM25 / SPLADE)** | rerank por términos exactos | Excelente para legal (los códigos y números importan: "art. 21.3.b") | rank_bm25, pyserini, opensearch | Determinista, sin GPU | No entiende sinónimos |
| **Híbrido denso+léxico** | RRF/weighted fusion | El default sensato para legal | LlamaIndex, Haystack, **BGE-M3 nativo** | Cubre ambos casos | Necesita tunear pesos |
| **GraphRAG (Microsoft)** | community detection + summaries jerárquicos por nivel | Bueno para "explica el panorama del derecho administrativo" | nano-graphrag, graphrag oficial | Razonamiento global | Indexación cara (LLM calls) — ~$200-500 para nuestro corpus, según Microsoft |
| **LightRAG** | dual-level (entity + relation) graph + vector híbrido | **Top en benchmarks de legal en 2025** (>80% acc vs 60-70% de baselines) | <https://github.com/HKUDS/LightRAG> | Más barato que GraphRAG; combina graph y vector | Aún joven (2024-2025) |
| **HippoRAG / HippoRAG 2** | Personalized PageRank sobre grafo de entidades inspirado en hipocampo | Bueno para multi-hop ("qué leyes derogadas afectan al art. 21 de la Ley 39/2015") | <https://github.com/OSU-NLP-Group/HippoRAG> | 10-30× más barato en multi-hop | Curva de aprendizaje |
| **RAPTOR** | clustering jerárquico de chunks | OK | LlamaIndex tiene módulo | Bueno para corpus muy grande | Nuestro corpus es pequeño |
| **ColBERT(v2)** | late interaction (token-level) | Excelente en precisión, caro en RAM/disco | RAGatouille | Top calidad | Index 2-5× más grande |
| **RAG sin vectores** | retrieval estructural Cypher + ranking LLM | Posible para queries con identificador concreto | DSPy + Neo4j | Cero infra vectorial | Falla en consultas semánticas |
| **Self-RAG / CRAG** | el LLM critica y re-recupera | Mejora calidad final | LangGraph, DSPy | Robustez | Latencia 2-3× |

#### 3.2 Propuesta para Reversa

**Pipeline en 4 etapas, orquestado con LlamaIndex + DSPy para optimización de prompts:**

```
1. Router (DSPy): clasifica la query → {factual, comparativa, agregada (briefing), narrativa}
                  → elige el camino

2. Retrieval híbrido:
   a) Cypher sobre Neo4j (si hay IDs/verbos detectados) → set estructural
   b) BGE-M3 dense + BGE-M3 sparse sobre Qdrant (con filtros pre: vigente=true si aplica)
   c) RRF de a + b
   d) Si la query es multi-hop: HippoRAG-style Personalized PageRank sobre el set fusionado para expandir vecindario

3. Rerank: bge-reranker-v2-m3 (mismo proveedor que BGE-M3, modelo cross-encoder ~568MB)

4. Generación + citas: prompt al LLM con chunks + obligación de citar
   con sintaxis `[BOE-A-YYYY-NNNNN#art21]`. Post-validación regex: descarta
   citas que no existen en el contexto. Devuelve fallback "no encuentro fundamento
   en el corpus" si no hay citas válidas.
```

**Por qué este mix:**
- **Las 4 briefings de GOAL son queries de grafo puro** → no necesitan vectores; resueltas con DuckDB/Cypher.
- **Las queries del usuario en chat son mixtas**: a veces piden un texto literal de un artículo (ColBERT/BM25 ganan), a veces piden "qué leyes regulan la protección de datos en el ámbito sanitario" (denso gana), a veces "leyes que dependen de la Ley 30/1992" (grafo gana).
- Híbrido + reranker es el patrón con mejor coste/beneficio en 2025.

#### 3.3 Embeddings — recomendación concreta

**Elegido: BGE-M3** (FlagEmbedding, BAAI). Razones:
- Multifuncional **en un solo forward pass**: dense + sparse (à la SPLADE) + ColBERT-like → cubre nuestras 3 necesidades.
- Multilingüe (100+ idiomas), excelente en español (validado en MIRACL).
- 8192 tokens de contexto → artículos largos completos sin trocear.
- Licencia MIT.
- **Despliegue local** sin GPU pesada con `FlagEmbedding` o `sentence-transformers`; con GPU 12GB hace ~500 chunks/s.
- Modelo: <https://huggingface.co/BAAI/bge-m3>, paper <https://arxiv.org/abs/2402.03216>.

**Alternativas evaluadas:**

| Modelo | Dim | Ctx | Coste | Pros | Contras |
|---|---|---|---|---|---|
| `multilingual-e5-large-instruct` | 1024 | 512 | local | Sólido en MIRACL | Solo denso; 512 tokens no caben artículos largos |
| `jina-embeddings-v3` | 1024 | 8192 | local (CC-BY-NC) | LoRA por tarea | **Licencia no comercial** — bloquea producción |
| OpenAI `text-embedding-3-large` | 3072 | 8191 | API ($0.13/M tokens) | Calidad alta | Coste recurrente, vendor lock-in, datos al exterior |
| Cohere `embed-multilingual-v3` | 1024 | 512 | API | Bueno en multilingüe | Coste, datos al exterior |
| Mistral `mistral-embed` | 1024 | 8192 | API | Decente | Coste, idem |

**Modelos legales en español** (los hay, no exhaustivos):
- **RoBERTalex** (PlanTL-GOB-ES / BSC-LT) — entrenado sobre 8.9 GB legal en español. <https://huggingface.co/PlanTL-GOB-ES/RoBERTalex>. **No es modelo de embeddings oracionales**, es masked LM tipo BERT. Útil si fine-tuneamos un encoder; **no plug-and-play**.
- **MEL — Legal Spanish Language Model** (arXiv 2501.16011, 2025) <https://arxiv.org/abs/2501.16011>. Generativo, no embedder.
- `mrm8488/legal-longformer-base-8192-spanish` — Longformer legal en español, 8k ctx. Adaptable a embeddings con pooling, pero requiere finetune.

**Decisión v1**: BGE-M3 directo. **v2**: evaluar finetunear BGE-M3 con pares (query, artículo) generados desde las propias consultas de usuario (señal de `:RECUPERA` + thumbs up/down).

#### 3.4 Citas precisas (no alucinables)

Obligatorias por GOAL.md y por compliance legal. Técnicas combinadas:

1. **JSON schema estricto** en la respuesta del LLM:
   ```json
   {"respuesta": "...", "citas": [{"id": "BOE-A-2015-10565", "articulo": "21", "extracto": "..."}]}
   ```
   Validado con Pydantic. Si el extracto no aparece literal en el chunk recuperado, **se rechaza la respuesta** y se reintenta el LLM call diciéndole qué cita es inválida.

2. **Function calling / tool use** del LLM: la generación no devuelve texto libre, sino una llamada a la herramienta `citar(norma_id, articulo, parrafo)`. Si el ID no existe en nuestro grafo, la herramienta devuelve error.

3. **Post-hoc grounding**: pasar la respuesta a un segundo LLM (más barato, p.ej. Haiku) con el contexto recuperado y preguntarle "¿cada afirmación está respaldada por una cita? Sí/No por afirmación". Heurística para detectar invenciones.

4. **UI**: cada cita renderizada como link clickable que abre el panel lateral del grafo con la norma; al hover muestra el extracto en hover-card.

#### 3.5 Framework de orquestación

| Framework | Overhead | Token-eff | Ergonomía RAG | Madurez | Veredicto |
|---|---|---|---|---|---|
| **LlamaIndex** | ~6 ms | 1.60k | Mejor para ingest+retrieval | 1ª clase | ✅ **Retrieval+indexing** |
| **DSPy** | ~3.5 ms (más bajo) | 2.0k | Optimización de prompts como código | Maduro 2025 | ✅ **Optimización de pipeline** |
| LangChain | ~10 ms | 2.4k | Verborreico, breaking changes frecuentes | Maduro pero inestable | ❌ — usar solo para `langgraph` si hace falta orquestar agentes |
| Haystack | ~5.9 ms | 1.57k | Pipelines declarativos, fortaleza en compliance legal/finance/govt | Maduro | Alternativa válida; rechazo por menor ecosistema de integraciones |
| nano-graphrag | n/a | n/a | Implementación mínima GraphRAG | Joven | Útil como referencia, no como dependencia |

**Decisión**: LlamaIndex (retrieval, document loaders, query engines) + DSPy (Router, Reflexión, optimización del prompt de generación final). Evitamos LangChain.

---

### 4. Frontend

#### 4.1 Framework web Python — comparativa

| Framework | Multipage real | File upload | Chat streaming | Custom JS lib (Sigma) | Madurez | Veredicto |
|---|---|---|---|---|---|---|
| **NiceGUI** | ✅ via `@ui.page('/graph')` | ✅ | ✅ SSE/WS | ✅ via `ui.html()` o componente custom | Activo, growing | ✅ **Elegido** |
| Streamlit | ✅ multipages, pero limitado | ✅ | ✅ `st.write_stream`, `st.chat_input` | ❌ iframe, sin events bidireccionales | Muy maduro | Descartado: `/graph` requiere componente custom complejo |
| Gradio | Limitada (Tabs) | ✅ | ✅ `gr.ChatInterface` | ❌ HTML estático | Maduro | Descartado mismo motivo |
| Reflex | ✅ Next.js-like, full pages | ✅ | ✅ | ✅ pero requiere wrapper | Maduro creciente | Alternativa fuerte; descartado por curva de aprendizaje y stack más pesado (compila a Next.js) |
| Dash (Plotly) | ✅ multipage v2.5+ | ✅ | Limitado | ✅ Dash Cytoscape | Muy maduro | Alternativa fuerte SI elegimos Cytoscape — ver §4.3 |
| Solara | ✅ | ✅ | ✅ | Posible | Joven | Descartado por ecosistema |
| Mesop | ✅ | ✅ | ✅ | Limitado | Joven | Descartado |
| FastAPI + Jinja + HTMX | ✅ rutas reales | ✅ | ✅ SSE | ✅ total libertad | Muy maduro | Plan B si NiceGUI no escala — más HTML manual |

**NiceGUI gana** porque permite `/chat` y `/graph` en la **misma app FastAPI**, integra Quasar/Vue para componentes ricos, soporta `ui.html()` para incrustar Sigma.js directamente, y mantiene una API Python pura sin generar archivos JS intermedios.

#### 4.2 Visualización del grafo

| Lib | Backend | Escala (nodos fluidos) | Integración Py | Eventos click | Veredicto |
|---|---|---|---|---|---|
| **Sigma.js** (vía `ipysigma` o wrapper custom) | WebGL | 100 k+ | `ipysigma` | ✅ | ✅ **Elegido** |
| Cytoscape.js (Dash Cytoscape) | Canvas/DOM | ~10–50 k | ✅ excelente | ✅ trivial (`tapNode`, `tapEdge`) | Plan B si elegimos Dash |
| Pyvis | vis.js | ~5 k | excelente | regular | Bueno para prototipo, no producción |
| Plotly + networkx | Plotly | ~3 k | trivial | limitado | Descartado |
| Bokeh | Canvas | ~5 k | trivial | limitado | Descartado |
| Graphistry | GPU (servidor) | 1M+ | API | excelente | Caro, freemium con límites; overkill |
| 3d-force-graph | WebGL | 50 k | manual | ✅ | Visualmente impresionante, sobreingeniería para legal |
| yFiles | comercial | excelente | wrapper | excelente | $$$, descartado |

Nuestro corpus (~12 k nodos) **cabe holgadamente en cualquiera**. Elegimos Sigma.js por:
- Render WebGL fluido incluso si v2 incorpora autonómicas y crecemos a >50 k.
- `ipysigma` ya devuelve eventos de click a Python.
- Estética cleaner que Cytoscape; mejor para SaaS.

**Patrón de renderizado para grafos grandes** (aunque no aplica todavía):
- **Ego-network rendering por defecto**: solo se muestra el vecindario (depth 2) del nodo seleccionado.
- **Expansión bajo demanda**: clic en nodo → backend devuelve aristas adicionales.
- **Level-of-detail**: con >5 k nodos visibles, colapsar comunidades en super-nodos (Louvain pre-calculado).
- **Filtrado server-side**: el sidebar de filtros (rango, fecha, vigente, materia) ejecuta una Cypher query y solo se envía el subgrafo resultante al cliente.

**Flujo UI confirmado:**
- `/` y `/chat` → chatbot (bienvenida "Bienvenido a Reversa!", input + uploader + send).
- Icono ▦ arriba-izq → navega a `/graph`.
- `/graph` → grafo Sigma + sidebar izq (filtros, búsqueda por ID) + sidebar derecho (panel desplegable que se abre al hacer click en nodo/arista).
- Estado conservado en server-side session (NiceGUI `app.storage.user`).

#### 4.3 Opciones del LLM

| Opción | Calidad ES jurídico | Latencia | Coste | Privacidad | Veredicto |
|---|---|---|---|---|---|
| **Anthropic Claude Sonnet 4.6 / Opus 4.7 (API)** | Top | 1-3 s | $3/$15 por M in/out tokens (Sonnet); más Opus | Datos al exterior | ✅ **Default** |
| OpenAI GPT-4.1 / o-series (API) | Alta | 1-3 s | $$ | Datos al exterior | Backup |
| Mistral Large (La Plateforme, API) | Alta en europeo | 1-2 s | $$ | EU-based | Alternativa con mejor narrativa de soberanía |
| **Local: Qwen2.5-32B-Instruct vía Ollama / vLLM** | Buena | 5-15 s en GPU 24 GB | $0 marginal | 100% local | ✅ **Fallback** |
| Local: Llama 3.3 70B-Instruct | Muy buena, pero 70 B pide 2× A100 | Alta | Hardware | Local | Solo si hay GPU enterprise |
| Local: Mistral Small 3 24B | Buena, eficiente | Media | Hardware | Local | Buena opción intermedia |

**Estrategia "sin saldo"**:
1. El cliente LLM detecta `402 Payment Required`, `429 Too Many Requests`, `insufficient_quota`.
2. Bandera global `llm_state = degraded`.
3. UI muestra banner: *"⚠ Cuota agotada en el proveedor principal. Respondiendo con modelo local (más lento, menos preciso)."*
4. Worker degrada automáticamente al modelo Ollama.
5. Si Ollama tampoco está disponible: deshabilita el chat, deja activa solo la búsqueda estructural sobre el grafo (sin generación).
6. Notificación al admin (Sentry/webhook) cuando se entra en degraded.

#### 4.4 Streaming de tokens

NiceGUI soporta tanto **SSE** (`ui.timer + ui.label.set_text`) como **WebSocket nativo** (NiceGUI usa WS internamente). El chat hace:
- Backend: `async for token in anthropic.messages.stream(...)`.
- Frontend: cada token actualiza un `ui.markdown` con `.refresh()`. Usuario ve la respuesta typewriter-style.

#### 4.5 Subida de archivos y parsing

| Tool | PDF complejo (tablas, footnotes) | DOCX | Idioma ES | Veredicto |
|---|---|---|---|---|
| **docling** (IBM) | ✅ Top 2025, layout-aware | ✅ | ES OK | ✅ **Elegido** para PDF/DOCX |
| pdfplumber | Decente | ❌ | OK | Backup para PDFs simples |
| pymupdf | Rápido | ❌ | OK | Backup |
| unstructured.io | ✅ pero hosted o pesado | ✅ | OK | Alternativa |
| PyPDF2 | Pobre con tablas | ❌ | OK | Descartado |

Política: límite 25 MB por archivo, máximo 5 archivos por consulta, MIME validado server-side, escaneo antivirus opcional (`clamav` vía socket, **[NUEVO]**), texto extraído enviado al pipeline RAG igual que una query.

---

### 5. Estructura final de `src/`

```
src/
├── __init__.py
├── main.py                        # punto de entrada: arranca FastAPI/NiceGUI + workers
│
├── config/
│   ├── __init__.py                # Settings (frozen Pydantic)
│   └── settings.py                # carga de .env, validación al inicio
│
├── api/                           # cliente HTTP de la API del BOE
│   ├── __init__.py                # exporta: BOEClient, BOEError
│   ├── client.py                  # httpx async + tenacity + aiolimiter
│   ├── models.py                  # Pydantic v2: Norma, Metadatos, Analisis, Referencia, Materia...
│   ├── endpoints.py               # rutas y helpers de URL
│   └── errors.py                  # ErrorBucket (retryable / permanent / parse)
│
├── ingesta/                       # orquestación de ingesta → raw
│   ├── __init__.py                # exporta: IngestaOrchestrator
│   ├── orchestrator.py            # async fan-out controlado
│   ├── incremental.py             # ingesta por ?from= usando fecha_actualizacion
│   ├── storage_raw.py             # escribe data/raw/{year}/{id}/*.json
│   └── retry_queue.py             # gestión de errors/*.jsonl
│
├── graph/                         # grafo de conocimiento
│   ├── __init__.py                # exporta: GraphStore, NormaNode, RelacionEdge, GraphLoader
│   ├── ontology.py                # definición de tipos de nodo/arista, vocabularios
│   ├── store_neo4j.py             # GraphStore concreto: Neo4j driver + Cypher
│   ├── store_inmem.py             # rustworkx in-memory + serialize/deserialize
│   ├── loader.py                  # raw JSON → nodos/aristas
│   ├── derived.py                 # computación del grafo derivado (PageRank, blast radius, communities)
│   └── briefings.py               # las 4 queries de GOAL implementadas
│
├── analytics/                     # DuckDB para queries columnares de briefings
│   ├── __init__.py                # exporta: AnalyticsStore
│   ├── store_duckdb.py            # esquemas y conexión
│   └── materialize.py             # Neo4j → DuckDB sync
│
├── rag/                           # retrieval-augmented generation
│   ├── __init__.py                # exporta: RAGPipeline, Retriever, Reranker, Generator
│   ├── chunking.py                # jerárquico por Libro/Título/Cap/Artículo
│   ├── embeddings.py              # wrapper de BGE-M3 (dense + sparse + colbert)
│   ├── vectorstore.py             # Qdrant local + filtrado por payload
│   ├── retriever_hybrid.py        # denso + léxico + Cypher → RRF
│   ├── retriever_graph.py         # HippoRAG-style PPR sobre rustworkx
│   ├── reranker.py                # bge-reranker-v2-m3
│   ├── generator.py               # cliente LLM con citas validadas (Pydantic schema)
│   ├── citation_guard.py          # post-hoc grounding + regex validator
│   └── pipeline.py                # orquestación con LlamaIndex + DSPy
│
├── llm/                           # adaptadores de LLM
│   ├── __init__.py                # exporta: LLMRouter, LLMError, OutOfCreditError
│   ├── router.py                  # selección Anthropic ↔ Ollama según estado
│   ├── anthropic_client.py
│   ├── ollama_client.py
│   └── state.py                   # llm_state (operational | degraded | down)
│
├── memory/                        # consultas de usuario como nodos
│   ├── __init__.py                # exporta: ConversationMemory
│   ├── store.py                   # nodos :Consulta, :Respuesta, aristas :RECUPERA, :CITA_EN_RESPUESTA, :GENERA
│   └── ttl.py                     # purga GDPR a 90 días
│
├── web/                           # frontend NiceGUI
│   ├── __init__.py                # exporta: create_app
│   ├── app.py                     # FastAPI app + NiceGUI mount
│   ├── pages/
│   │   ├── __init__.py
│   │   ├── chat.py                # /  y  /chat — bienvenida, input, uploader, historial
│   │   └── graph.py               # /graph — Sigma.js viewer, filtros, panel lateral
│   ├── components/
│   │   ├── __init__.py
│   │   ├── chat_bubble.py
│   │   ├── citation_chip.py       # link clickeable a /graph?node=BOE-A-...
│   │   ├── file_uploader.py
│   │   ├── graph_canvas.py        # wrapper de Sigma.js
│   │   └── node_panel.py          # panel lateral derecho
│   └── static/
│       └── sigma_bridge.js        # único JS, glue para eventos click → Python
│
├── parsers/                       # extracción de texto de uploads del usuario
│   ├── __init__.py                # exporta: parse_file
│   └── docling_parser.py
│
├── observability/                 # [NUEVO]
│   ├── __init__.py
│   ├── logging.py                 # structlog + correlation id por request
│   ├── metrics.py                 # Prometheus
│   └── tracing.py                 # OpenTelemetry export a Jaeger/Tempo
│
└── cli/                           # comandos invocables: python -m reversa.cli
    ├── __init__.py                # exporta: app (typer)
    ├── ingesta_cmd.py             # `reversa ingesta full | incremental | retry-failed`
    ├── briefings_cmd.py           # `reversa briefings 1|2|3|4`
    └── admin_cmd.py               # `reversa admin dump-graph | restore | wipe-memory`

tests/
├── conftest.py
├── unit/
│   ├── test_api_client.py
│   ├── test_graph_loader.py
│   ├── test_chunking.py
│   ├── test_citation_guard.py
│   ├── test_llm_router_degradation.py
│   └── ...
├── integration/
│   ├── test_boe_real.py           # @pytest.mark.integration
│   ├── test_neo4j_briefings.py    # testcontainers
│   ├── test_qdrant_retrieval.py
│   └── test_end_to_end_rag.py
└── e2e/
    ├── conftest.py                # playwright fixtures
    ├── test_chat_flow.py
    └── test_graph_navigation.py
```

#### `__init__.py` — exports principales

```python
# src/api/__init__.py
from .client import BOEClient
from .errors import BOEError, RetryableError, PermanentError, ParseError
from .models import Norma, Metadatos, Analisis, Referencia, Materia
__all__ = ["BOEClient", "BOEError", "RetryableError", "PermanentError",
           "ParseError", "Norma", "Metadatos", "Analisis", "Referencia", "Materia"]
```

```python
# src/graph/__init__.py
from .store_neo4j import GraphStore
from .store_inmem import InMemoryGraph
from .ontology import NormaNode, RelacionEdge, RELACION_CODES
from .loader import GraphLoader
from .briefings import top_amended, top_amenders, dead_law_rot, blast_radius
__all__ = ["GraphStore", "InMemoryGraph", "NormaNode", "RelacionEdge",
           "RELACION_CODES", "GraphLoader", "top_amended", "top_amenders",
           "dead_law_rot", "blast_radius"]
```

```python
# src/rag/__init__.py
from .pipeline import RAGPipeline
from .retriever_hybrid import HybridRetriever
from .reranker import Reranker
from .generator import Generator
from .chunking import HierarchicalChunker
from .embeddings import BGEM3Embedder
from .vectorstore import QdrantStore
__all__ = ["RAGPipeline", "HybridRetriever", "Reranker", "Generator",
           "HierarchicalChunker", "BGEM3Embedder", "QdrantStore"]
```

```python
# src/llm/__init__.py
from .router import LLMRouter
from .state import LLMState
from .anthropic_client import AnthropicClient
from .ollama_client import OllamaClient
__all__ = ["LLMRouter", "LLMState", "AnthropicClient", "OllamaClient",
           "LLMError", "OutOfCreditError"]
from .router import LLMError, OutOfCreditError  # noqa: E402
```

```python
# src/web/__init__.py
from .app import create_app
__all__ = ["create_app"]
```

#### `src/main.py`

```python
"""Reversa entry point.

Arranca el servidor web (NiceGUI + FastAPI), inicia el GraphStore en background,
hidrata el grafo derivado en memoria y deja al sistema listo para servir
consultas en /chat y /graph.
"""

from __future__ import annotations

import asyncio
from typing import NoReturn

import uvicorn

from reversa.config import settings
from reversa.observability import setup_logging
from reversa.graph import GraphStore, InMemoryGraph
from reversa.web import create_app


async def _warmup(store: GraphStore, mem: InMemoryGraph) -> None:
    """Carga el grafo de Neo4j a memoria al arrancar."""
    await mem.hydrate_from(store)


def main() -> NoReturn:
    """Arranca el sistema entero."""
    setup_logging(level=settings.log_level)
    store = GraphStore.from_settings(settings)
    mem = InMemoryGraph()
    asyncio.run(_warmup(store, mem))
    app = create_app(store=store, in_memory_graph=mem)
    uvicorn.run(app, host=settings.host, port=settings.port, log_config=None)


if __name__ == "__main__":
    main()
```

---

### 6. Cosas no contempladas inicialmente [NUEVO]

Marcado como "no estaba en el prompt", evaluado por iniciativa:

1. **Observabilidad** (logging estructurado, métricas Prometheus, tracing OpenTelemetry) — sin esto no se diagnostica un fallo en producción.
2. **Versionado de datos** con **DVC** sobre `data/raw/` — el corpus es la verdad; queremos saber qué snapshot estaba en producción cuando se respondió a una consulta.
3. **GDPR / privacidad** sobre las consultas de usuario (cifrado, TTL, derecho de borrado).
4. **Evaluación del RAG**: `ragas` o `deepeval` para construir un golden set de 50-100 preguntas con respuestas y citas verificadas; correr en CI.
5. **LLM observability**: `Langfuse` o `Arize Phoenix` para trazar cada llamada (prompt, contexto, respuesta, coste, latencia, feedback usuario).
6. **Caché de respuestas LLM**: queries idénticas no deberían pagar el LLM dos veces. Caché por hash(query + retrieved_ids + model + version).
7. **Feature flags**: para activar/desactivar GraphRAG vs vector-only, modelo LLM, etc., sin redeploy.
8. **Auth y multi-tenancy**: si esto va a una demo pública, mínimo rate limit por IP. Si es interno, OAuth contra Google Workspace / Microsoft Entra.
9. **CI/CD**: GitHub Actions con `make check` + `make test` + `pip-audit` + `playwright install` antes de PRs.
10. **Backups automáticos** de Neo4j (`neo4j-admin database dump` cron diario → S3/B2).
11. **Docker compose** para dev local que arranque Neo4j, Qdrant y Ollama de un golpe — onboarding en minutos.
12. **Estrategia de versionado de embeddings**: si cambiamos de BGE-M3 a otro modelo, hay que reindexar TODO. Almacenar `embedding_version` en cada vector.
13. **Detección de drift del schema BOE**: la API puede añadir verbos nuevos o cambiar formatos. Job nocturno que compara el catálogo de `relaciones-anteriores` con el snapshot anterior y alerta si hay diff.
14. **Internacionalización de la UI**: por ahora todo en español (es el corpus); preparar i18n por si en el futuro se exporta el patrón a otros boletines (UE, LatAm).
15. **Modo "diff" de normas**: dado un `BOE-A-id`, mostrar visualmente qué cambió artículo a artículo entre versiones consolidadas — útil para juristas, no pedido en GOAL pero golpe seguro de "surprise us".
16. **"Surprise" para el Council** (cumple la última línea de GOAL.md): un mapa de calor temporal del *churn legislativo por departamento por año* — quién fue el departamento más caótico cada legislatura. Visualmente potente, calculable con DuckDB en milisegundos.

---

### 7. Librerías a instalar

Comandos `uv add` agrupados. **No ejecutar todo de golpe**; aplicar por hito.

```bash
# --- Hito 1: API + ingesta ---
uv add httpx[http2] tenacity aiolimiter pydantic pydantic-settings \
       orjson lxml hishel structlog python-dotenv typer

uv add --dev pytest pytest-asyncio pytest-cov pytest-mock respx \
             freezegun ruff mypy pylint complexipy pip-audit

# --- Hito 2: grafo ---
uv add neo4j rustworkx duckdb

# --- Hito 3: RAG ---
uv add llama-index llama-index-vector-stores-qdrant qdrant-client \
       FlagEmbedding sentence-transformers torch \
       rank-bm25 dspy-ai
# bge-reranker-v2-m3 se descarga vía sentence-transformers/HF

# --- Hito 4: LLM clients ---
uv add anthropic openai ollama mistralai

# --- Hito 5: frontend ---
uv add nicegui ipysigma docling markdownify

# --- Hito 6: observabilidad y eval ---
uv add prometheus-client opentelemetry-api opentelemetry-sdk \
       opentelemetry-instrumentation-fastapi opentelemetry-instrumentation-httpx \
       langfuse ragas

# --- Hito 7: dev infra ---
uv add --dev testcontainers playwright dvc
```

**Notas:**
- `torch` puede instalarse en CPU-only o CUDA según hardware: `uv add --index https://download.pytorch.org/whl/cpu torch` para CPU.
- `playwright install chromium` se ejecuta una vez por entorno (no es `uv add`).
- `nicegui` ya trae FastAPI y uvicorn como dependencia transitiva — no añadirlas duplicadas.
- `FlagEmbedding` es el paquete oficial de BAAI para BGE-M3 (alternativa: `sentence-transformers` con `BAAI/bge-m3`).

---

### 8. Fuentes (verificadas hoy 2026-05-27)

**API del BOE**
- API portal: <https://www.boe.es/datosabiertos/api/api.php>
- Documentación legislación consolidada (PDF): `resources/datos_boe.pdf` (incluido en repo) y <https://www.boe.es/datosabiertos/documentos/APIconsolidada.pdf>
- FAQ datos auxiliares: <https://www.boe.es/datosabiertos/faq/datos-auxiliares.php>
- Catálogo datos.gob.es: <https://datos.gob.es/en/catalogo/ea0040819-legislacion-consolidada-de-la-agencia-estatal-boe>
- Repos comunidad: <https://github.com/ComputingVictor/MCP-BOE>

**Ontologías legales**
- Palantir Foundry Ontology overview: <https://www.palantir.com/docs/foundry/ontology/overview>
- Ontology System Architecture: <https://www.palantir.com/docs/foundry/architecture-center/ontology-system>
- 3 capas explicadas: <https://pythonebasta.medium.com/understanding-palantirs-ontology-semantic-kinetic-and-dynamic-layers-explained-c1c25b39ea3c>
- Akoma Ntoso (OASIS): <https://www.oasis-open.org/committees/legaldocml/>
- ELI ↔ AKN mapping: <https://dl.acm.org/doi/10.1145/3614321.3614327>
- ELI overview Sparna: <https://www.sparna.fr/en/references/european-legislation-identifier-eli/>
- Repo curado de ontologías legales: <https://github.com/Liquid-Legal-Institute/Legal-Ontologies>

**Bases de datos grafo**
- Neo4j alternatives 2026 (ArcadeDB blog): <https://arcadedb.com/blog/neo4j-alternatives-in-2026-a-fair-look-at-the-open-source-options/>
- Memgraph vs Neo4j: <https://memgraph.com/blog/neo4j-vs-memgraph>
- rustworkx paper (arXiv 2110.15221): <https://arxiv.org/abs/2110.15221>

**RAG**
- LightRAG paper/repo: <https://github.com/HKUDS/LightRAG>
- LightRAG vs GraphRAG: <https://www.analyticsvidhya.com/blog/2025/01/lightrag/>
- HippoRAG: <https://github.com/OSU-NLP-Group/HippoRAG>
- GraphRAG (Microsoft) repo: <https://github.com/microsoft/graphrag>
- Comparativa frameworks RAG 2025-26: <https://iternal.ai/blockify-rag-frameworks>
- Chunking estrategias para legal (paper 2025): <https://arxiv.org/html/2510.06999v1>

**Embeddings**
- BGE-M3 modelo: <https://huggingface.co/BAAI/bge-m3>
- BGE-M3 paper: <https://arxiv.org/abs/2402.03216>
- jina-embeddings-v3 paper: <https://arxiv.org/abs/2409.10173>
- multilingual-e5: <https://huggingface.co/intfloat/multilingual-e5-large-instruct>
- RoBERTalex (legal ES): <https://huggingface.co/PlanTL-GOB-ES/RoBERTalex>
- MEL: Legal Spanish LM: <https://arxiv.org/abs/2501.16011>
- legal-longformer-base-8192-spanish: <https://huggingface.co/mrm8488/legal-longformer-base-8192-spanish>

**Visualización**
- Sigma.js: <https://www.sigmajs.org/>
- ipysigma: <https://github.com/medialab/ipysigma>
- Dash Cytoscape: <https://dash.plotly.com/cytoscape>
- Comparativa libs JS: <https://www.pkgpulse.com/blog/cytoscape-vs-vis-network-vs-sigma-graph-visualization-javascript-2026>

**Frontend Python**
- NiceGUI: <https://nicegui.io/>
- Streamlit vs NiceGUI: <https://www.bitdoze.com/streamlit-vs-nicegui/>
- Reflex: <https://reflex.dev/>
- Comparativa frameworks 2025: <https://anvil.works/articles/top-python-web-app>

**HTTP / async**
- httpx: <https://www.python-httpx.org/>
- tenacity: <https://tenacity.readthedocs.io/>
- aiolimiter: <https://github.com/mjpieters/aiolimiter>
- hishel: <https://hishel.com/>
