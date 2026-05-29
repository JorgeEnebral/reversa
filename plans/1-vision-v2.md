# Reversa — Plan arquitectónico v2 (1-vision-v2.md)

> v2 sobre [`1-vision-v1.md`](./1-vision-v1.md). Las decisiones aquí **sobrescriben** a las de v1; lo que no se mencione, se mantiene.
>
> Norte: **overfitting al GOAL.md**, a los 4 briefings. Cero overengineering.
> **Sin contenedores** (Docker / testcontainers fuera).

---

## Prompt

> Crea una v2 de 1-vision-v1.md. Al inicio del documento pon el prompt, y a continuación las librerias a descargar manualmente con uv. No usar contenedores.
>
> Todo lo que viene a continuación es el nuevo plan que hay que crear sobre v1. Si dice algo que hacer y entra en contradiccion con v1, esto tiene prioridad. Si no se menciona es que se mantiene lo de v1.
>
> El objetivo es hacer overfitting al GOAL.md, a los 4 briefings.
> Crear un fichero config.py en src/ con las configuraciones de cada una de las clases.
>
> - API - Demasiada para principalmente hacer la descarga masiva una vez.
>     - Se obtienen primero todos ids de las normas a partir de /legislacion-consolidada, se guardan en un fichero txt uno por linea y de ahí se obtiene obtiene todo el xml junto (Metadatos, analisis, texto) si hay una alternativa mejor dila.
>     - Descarga todo, imagenes y tablas incluido. Metadata eli no lo toques, eso se puede olvidar.
>     -  Siempre descargar de fecha mas antigua a mas nueva para que no haya errores.
>     - Cubrir solo la API de legislación consolidada. No tablas auxiliares, etc....
>     - Tampoco usar rate limiting, backoff exponencial, user-agent identificable, cache
>     - Mantener que las peticiones erroras guardarlas en data_api/errors/.
>     - Guardar el resto en data_api/raw/YYYY/nombre.xml
>     - Actualizar tests. Para las descargas de los tests que se guarden las descargas en data-api/tests/. Y cuando se termine de ejecutar que se borre el directorio.
>     - Sin DVC
>     - Añadir una funcion reintentar, en la que se reintente los que tienen errores, si los consigue los borra de data_api/errores. Tiene que reportar los conseguidos del total.
>     - Al final, debe haber 3 formas de llamar: la masiva (gestionada por completo, tiene que cumplir siempre), la de reintentar, y una selectiva, donde metiendo una lista de ids los guarda
> - Preprocesado y BBDD
>     - Usar solo Neo4J por simplicidad. No usar DuckDB. La libreria Scigraph para que sirvr?
>     - Para el preprocesado parsear el xml los atributos seleccionados en config.py (se ponen todos los que pueden estar en un xml y si se pone True los parsea para guardarlos y si es False los ignora). Siempre preprocesar de fecha mas antigua a mas nueva para que no haya errores.
>     - Al final se meten los datos a Neo4J y se crea en la carpeta data/ontology/semantic-layer/ el esquema de cada tipo de nodo (norma con todos sus atributos) y aristas (verbos de texto anterior (SOLO ANTERIOR, PARA NO TENER REDUNDANCIA), los relevantes para el briefing).
>     - En config.py se ponen los codigos a relacionar, el resto se ignoran. Se
>     - Olvidar doble grafo raw y derivado. No usar RAG ni embeddings. Ni chunking. Es overengineering.
>     - Usar la ontologia A para el caso. Crear en la carpeta data/ontology/dynamic-layer/ los esquemas de la capa dinamica en la que el usuario interactura con la ontologia subyacente:  añadir un nodo del tipo query_usuario, con su id, el prompt que metio el usuario, la respuesta del modelo, y la lista de nodos de la capa semantica a los que se enlaza. Y el esquema de las aristas tipo response_edge con atributos id_query_usuario, id nodo con el que enlaza. está relacionado a los nodos de la respuesta con una arista del tipo Responde_Edge.
>     - Sigue siendo necesario rustworkx con esto para visualizar en la web?
>     - Quita GDPR
>     - Haz tests del preprocesado y de la carga a neo4j
> - Frontend
>     - Hacerlo con NiceGUI y sigma.js
>     - En chat/
>         - Interfaz como la de cualquier SaaS IA: claude, gemini, ChatGPT -> Saludo de "Bienvenido a Reversa!" Debajo un espacio para introducir texto (que se adapta al tamaño del texto) y a la derecha un boton de enviar. No se pueden cargar documentos. Tiene que aparecer la informacion en steaming proporcionada por el LLM.
>         - El LLM por detrás que mapeará la query del usuario a peticiones al backend y devolverá la respuesta al usuario sera claude Haiku, y el prompt de sistema indicará informacion relevante para mapear del LLM a backend.. En src/llm/ he puesto un codigo de un certificado introductorio de claude. Haz un analisis de él y quédate de ahi con lo realmente interesante, lo que no se use dilo para eliminarlo. No usar tools ni mcps.
>     - En graph/
>         - Inicialmente mostrar todo el grafo. Se puede hacer zoom y deshacer, moverse. Visualizacion dinamica.
>         - Cuando se clica en uno en la parte derecha aparece un desplegable con toda la info del nodo. Si es una arista igual: información de la arista (que accion hace), que nodo actua y cual es el pasivo. Tiene una X arriba a la izquierda para cerrar el campo de información.
>         - En la parte izquierda siempre estará el campo de filtros. En los filtros aparecen los atributos de nodos y aristas. Los los atributos que están en el esquema de la ontologia (semantica y dinamica). Cada atributo tiene su campo de busqueda especifico por el que buscar. Abajo tiene un campo de aplicar para que se actualice. Y otro al lado (izqueirda) de aplicar llamado reestablecer para que salga de nuevo todo el grafo. Los filtros se añaden a la URL con /graph?filtros.... Se tiene que poder filtrar también por los nodos query_usuario (por defecto aparecen con el resto del grafo, pero se debe poder seleccionar que salgan todos, o uno o varios de ellos.)
>
> Rehaz la estructura final de src/ con todas las simplificaciones

---

## Librerías a descargar manualmente con uv

> Ejecutar **en orden, paso a paso**. Cada bloque corresponde a un hito del plan; no instalar todo de golpe.

```bash
# --- Hito 1: API (descarga masiva) ---
uv add httpx lxml pydantic pydantic-settings python-dotenv typer structlog

# --- Hito 2: Preprocesado + Neo4j ---
uv add neo4j

# --- Hito 3: LLM (chat) ---
uv add anthropic

# --- Hito 4: Frontend (NiceGUI + Sigma.js) ---
uv add nicegui ipysigma

# --- Dev tools (transversales) ---
uv add --dev pytest pytest-asyncio pytest-mock respx ruff mypy pylint complexipy pip-audit
```

**Notas:**
- `httpx` se usa en modo **sync**. No hay async porque no hay concurrencia, ni rate limit, ni backoff (decisión del prompt).
- `pydantic-settings` se mantiene solo porque `config.py` requiere un objeto frozen tipado para las flags por clase.
- `ipysigma` integra Sigma.js (WebGL) dentro de NiceGUI vía `ui.html` + bridge JS mínimo.
- **Fuera** respecto a v1: `tenacity`, `aiolimiter`, `orjson`, `hishel`, `rustworkx`, `duckdb`, `qdrant-client`, `llama-index*`, `FlagEmbedding`, `sentence-transformers`, `torch`, `rank-bm25`, `dspy-ai`, `openai`, `ollama`, `mistralai`, `docling`, `markdownify`, `langfuse`, `ragas`, `prometheus-client`, `opentelemetry-*`, `testcontainers`, `playwright`, `dvc`.
- **Sin contenedores**: Neo4j Community debe estar instalado de forma nativa en el host (`brew install neo4j` / `apt install neo4j` / `wsl`); los tests de integración apuntan a esa instancia local con base de datos `reversa_test` separada.

---

## Plan

### 1. API — descarga masiva única

#### 1.1 Por qué la simplificación es correcta

La API se llama **una vez al mes** (o menos: el corpus consolidado cambia despacio). 12 285 normas → con conexión doméstica + servidor BOE responsive (~100 ms/req) son **~20 min** secuenciales. Sobra. No hace falta async, ni token bucket, ni HTTP/2 — sí hace falta **terminar**, persistir lo que falló y poder reintentar.

#### 1.2 Flujo de descarga masiva

```
Paso 1 ─ Listado de IDs
─────────────────────────
GET /legislacion-consolidada?limit=-1
  Accept: application/json
  → respuesta: lista completa con (identificador, fecha_publicacion)
  → ordenar por fecha_publicacion ascendente (más antigua → más nueva)
  → persistir en data_api/raw/ids.txt    (un ID por línea, en ese orden)
  (devuelve un límite de 10K, ejecutar hasta obtener todos)

Paso 2 ─ Descarga de norma completa
────────────────────────────────────
Para cada id en ids.txt (en orden):
  GET /legislacion-consolidada/id/{id}
    Accept: application/xml
    → respuesta: XML con <metadatos>, <analisis>, <metadata-eli>, <texto>
      (incluye <img> en base64 e <table> HTML, todo embebido)
  Año = parseado de fecha_publicacion del XML (o del id BOE-A-YYYY-...)
  Persistir en data_api/raw/{YYYY}/{id}.xml

  Si excepción (HTTP != 200, timeout, XML inválido):
    Persistir en data_api/errors/{id}.json con
      {id, timestamp, status, error, attempt}
```

**¿Hay alternativa mejor que `/id/{id}` para conseguir todo de golpe?**

Sí, ya es la mejor opción. La documentación oficial confirma que `/id/{id}` devuelve **el XML completo con los 4 bloques** (`<metadatos>`, `<analisis>`, `<metadata-eli>`, `<texto>`) en una sola respuesta. Las alternativas (`/metadatos`, `/analisis`, `/texto/bloque/{id}`) requerirían **3+ llamadas por norma** y solo dan JSON en algunas. Una llamada por norma a `/id/{id}` es lo más eficiente.

`<metadata-eli>` viene incluido en la respuesta pero **lo ignoramos** al parsear (decisión del prompt). El bloque queda en el XML serializado pero no se procesa.

#### 1.3 Ordenación temporal antigua → nueva

Crítica para no romper el grafo: cuando una norma N₂ tiene en su `<analisis><referencias><anteriores>` una norma N₁, queremos que N₁ ya exista cuando insertamos N₂. La fuente canónica del orden temporal es `fecha_publicacion` del listado. El orden se aplica:
- **En descarga**, para que el reintento tenga la misma topología que la ingesta inicial.
- **En preprocesado** (sección 2), para que la carga a Neo4j tampoco intente referenciar nodos que aún no existen.

#### 1.4 Lo que se quita respecto a v1

| Quitado | Por qué |
|---|---|
| Rate limiting (`aiolimiter`) | API no documenta límite; descarga es batch, no concurrente |
| Backoff exponencial (`tenacity`) | Si falla se va a `errors/`; el reintento es manual |
| User-Agent identificable | No exigido; httpx por defecto basta |
| Cache (`hishel`) | Innecesario — la descarga es one-shot, sin recurrencia |
| DVC | Versionado innecesario para una BD que se reconstruye desde el dump XML |
| Tablas auxiliares (`/datos-auxiliares/*`) | No hace falta — los códigos de relación y rango se hardcodean (53 verbos + 19 rangos están en `docs/estructura_leyes-v1.md`) |
| Sumarios BOE / BORME | No hace falta para los 4 briefings |

#### 1.5 Gestión de errores

Una única carpeta plana:

```
data_api/errors/
  ├── BOE-A-1996-15367.json
  ├── BOJA-b-2020-90390.json
  └── ...
```

Formato del fichero:

```json
{
  "id": "BOE-A-1996-15367",
  "timestamp": "2026-05-29T08:42:11Z",
  "status_code": 503,
  "error": "Service Unavailable",
  "attempts": 1
}
```

Cuando se reintenta y se consigue, se borra ese fichero y el XML se persiste en `data_api/raw/YYYY/`.

#### 1.6 Las tres entradas de uso

```python
# src/api/downloader.py
class BOEDownloader:
    def descargar_masivo(self) -> ResumenDescarga: ...
    def reintentar(self) -> ResumenReintento: ...
    def descargar_selectivo(self, ids: list[str]) -> ResumenDescarga: ...
```

- **`descargar_masivo()`** — pipeline completo. Idempotente: si `data_api/raw/ids.txt` ya existe, **no** lo re-pide (a menos que se pase `force=True`). Para cada ID, si el XML ya está en `data_api/raw/YYYY/{id}.xml`, **lo salta**. Si falló previamente y está en `errors/`, **lo reintenta** (lo más natural). Al final reporta `total / descargados / fallidos / saltados`.

- **`reintentar()`** — lee solo los IDs en `data_api/errors/`, los reintenta uno a uno. Cada éxito: borra el fichero de `errors/` y guarda el XML en `raw/YYYY/`. Cada fallo: incrementa `attempts` en el JSON de errors. **Reporta `recuperados / total_intentados`** como pide el prompt.

- **`descargar_selectivo(ids: list[str])`** — descarga la lista proporcionada y la guarda en `raw/YYYY/`, mismo manejo de errores. Útil para ingesta puntual de una norma nueva sin re-pedir las 12 k.

CLI (`typer`):

```bash
python -m reversa.cli api masivo
python -m reversa.cli api reintentar
python -m reversa.cli api selectivo --ids BOE-A-2015-10565,BOE-A-2015-10566
python -m reversa.cli api selectivo --from-file ids_extras.txt
```

#### 1.7 Tests del cliente (`tests/unit/api/` + `tests/integration/api/`)

Mock HTTP con **`respx`** (mock nativo de httpx, sigue siendo la mejor opción incluso en modo sync).

**Casos cubiertos:**

| Test | Tipo | Qué verifica |
|---|---|---|
| `test_lista_ids_ordenada_por_fecha` | unit | Orden ascendente por `fecha_publicacion` |
| `test_lista_ids_persiste_en_txt` | unit | `data_api/tests/raw/ids.txt`, 1 ID por línea |
| `test_descarga_id_persiste_en_raw_year` | unit | `BOE-A-2015-10565` → `data_api/tests/raw/2015/BOE-A-2015-10565.xml` |
| `test_descarga_id_404` | unit | Se persiste en `errors/{id}.json` con `status_code: 404` |
| `test_descarga_id_500_no_reintenta_internamente` | unit | Se persiste en `errors/` directamente; **no hay backoff** |
| `test_xml_invalido` | unit | Persistido en `errors/` con `error: "ParseError"` |
| `test_skip_si_ya_descargado` | unit | Idempotencia: 2ª pasada no hace request |
| `test_reintentar_recupera_y_borra` | unit | Reintentar éxito → fichero desaparece de `errors/`, aparece en `raw/` |
| `test_reintentar_reporta_recuperados` | unit | Devuelve `(recuperados, total_intentados)` |
| `test_selectivo_lista` | unit | Lista de IDs proporcionada se descarga; sin re-pedir listado completo |
| `test_descarga_real_norma_conocida` | integration (`@pytest.mark.integration`) | Bajar Ley 39/2015 contra la API real, verificar que el XML contiene `<metadatos>`, `<analisis>`, `<texto>` |

**Convención de carpetas de tests** (decisión del prompt):
- Todas las descargas de tests van a `data_api/tests/raw/` y `data_api/tests/errors/`.
- `conftest.py` define una fixture `boe_test_dir` que crea esa estructura y, en `finalize`, **borra `data_api/tests/` por completo** (`shutil.rmtree`).
- Sin testcontainers (no contenedores).

```python
# tests/conftest.py
import shutil
from pathlib import Path
import pytest

@pytest.fixture
def boe_test_dir(tmp_path_factory):
    base = Path("data_api/tests")
    (base / "raw").mkdir(parents=True, exist_ok=True)
    (base / "errors").mkdir(parents=True, exist_ok=True)
    yield base
    shutil.rmtree(base, ignore_errors=True)
```

---

### 2. Preprocesado + BBDD

#### 2.1 BBDD única: Neo4j

DuckDB fuera. Las 4 briefings son **queries Cypher puras** sobre el grafo:

```cypher
// Briefing 1 — top 5 normas más modificadas (in-degree por verbos modificación)
MATCH (a:Norma)-[r]->(b:Norma)
WHERE type(r) IN ['MODIFICA','MODIFICA_DET','AÑADE','SUSTITUYE','SUPRIME']
RETURN b.id AS norma, count(r) AS n_mods
ORDER BY n_mods DESC LIMIT 5;

// Briefing 2 — top 5 normas que más modifican (out-degree)
MATCH (a:Norma)-[r]->(b:Norma)
WHERE type(r) IN ['MODIFICA','MODIFICA_DET','AÑADE','SUSTITUYE','SUPRIME']
RETURN a.id AS norma, count(r) AS n_mods_realizadas
ORDER BY n_mods_realizadas DESC LIMIT 5;

// Briefing 3a — % de normas vivas que citan al menos una derogada
MATCH (viva:Norma {vigente:true})-[:CITA|DEROGA|MODIFICA|DESARROLLA]->(otra:Norma)
WITH viva, sum(CASE WHEN otra.vigente=false THEN 1 ELSE 0 END) AS muertas_citadas
WITH count(viva) AS total_vivas,
     sum(CASE WHEN muertas_citadas > 0 THEN 1 ELSE 0 END) AS vivas_con_muertas
RETURN 100.0 * vivas_con_muertas / total_vivas AS porcentaje;

// Briefing 3b — top 5 normas muertas más citadas por normas vivas
MATCH (viva:Norma {vigente:true})-[r:CITA|DEROGA|MODIFICA|DESARROLLA]->(muerta:Norma {vigente:false})
RETURN muerta.id AS norma_muerta, count(viva) AS citas
ORDER BY citas DESC LIMIT 5;

// Briefing 4 — blast radius Ley 30/1992
MATCH (viva:Norma {vigente:true})-[r:CITA]->(:Norma {id:'BOE-A-1992-26318'})
RETURN viva.id, viva.titulo;
```

**¿SciGraph para qué sirve?**

[SciGraph](https://github.com/SciGraph/SciGraph) es una librería **Java** (no Python) del NCATS biomédico que importa ontologías OWL/RDF/OBO/TTL a Neo4j usando `owlapi`. Está pensada para grafos del mundo biomédico (Monarch Initiative). **Para Reversa no aporta nada**: nuestra "ontología" es plana (un único tipo de nodo, aristas tipadas por código de relación), no tenemos ningún fichero OWL/RDF, y no necesitamos resolución de CURIEs ni autocomplete de vocabularios. **Descartado: usar el driver oficial de Neo4j directamente.**

#### 2.2 Parseado XML dirigido por `config.py`

```python
# src/config.py — extracto
class ParseFlags(BaseModel):
    # Flags por atributo de <metadatos> — True = parsea y guarda, False = ignora
    fecha_actualizacion: bool = False   # solo útil en re-ingesta incremental, descartable
    identificador:       bool = True
    ambito_codigo:       bool = True
    departamento_codigo: bool = True
    departamento_texto:  bool = True
    rango_codigo:        bool = True
    rango_texto:         bool = True
    fecha_disposicion:   bool = True
    numero_oficial:      bool = True
    titulo:              bool = True
    diario:              bool = False    # constante para estatales
    fecha_publicacion:   bool = True
    diario_numero:       bool = False
    fecha_vigencia:      bool = True
    estatus_derogacion:  bool = True
    fecha_derogacion:    bool = True
    estatus_anulacion:   bool = True
    fecha_anulacion:     bool = True
    vigencia_agotada:    bool = True
    estado_consolidacion_codigo: bool = True
    url_eli:             bool = True
    url_html_consolidada: bool = False   # reconstruible desde identificador

    # Bloque <analisis>
    materias:            bool = True
    notas:               bool = False    # texto libre, no estructural
    referencias_anteriores: bool = True   # ← lo que alimenta el grafo
    referencias_posteriores: bool = False  # ← FALSE: redundante con anteriores (decisión del prompt)

    # Bloque <texto> — no se parsea para el grafo en v2
    texto_bloques:       bool = False
```

**Solo `referencias_anteriores`** alimentan el grafo. La razón: en la API, cada relación aparece **dos veces** (en `<anteriores>` de la norma que actúa, y en `<posteriores>` de la norma que la recibe). Procesar solo el lado activo elimina la redundancia y simplifica el código.

**Códigos de relación a materializar como aristas** — también en `config.py`:

```python
class RelacionConfig(BaseModel):
    # Códigos de relación que generan arista. El resto se ignoran.
    # Cada código se mapea a un nombre de relación Cypher (TYPE en Neo4j).
    codigos_a_relacion: dict[int, str] = {
        210: "DEROGA",
        211: "DEROGA_LO_INDICADO",
        212: "DEROGA_CON_EXCEPCION",
        213: "DEROGA_EN_CUANTO_SE_OPONGA",
        214: "DEROGA_EN_FORMA_INDICADA",
        215: "DEROGA_PARCIALMENTE",
        216: "DEROGA_REITERADA",
        217: "DEROGA_TACITAMENTE",
        270: "MODIFICA",
        271: "MODIFICA_PLAN",
        272: "MODIFICA_DET",
        235: "SUPRIME",
        245: "SUSTITUYE",
        407: "AÑADE",
        330: "CITA",
        331: "EN_RELACION_CON",
        490: "DESARROLLA",
        420: "APRUEBA",
        426: "TRANSPONE",
        427: "TRANSPONE_PARCIALMENTE",
    }
```

Estos 20 códigos cubren los 4 briefings (`MODIFICA*`+`AÑADE`+`SUSTITUYE`+`SUPRIME` para 1-2, `DEROGA*` para 3-4, `CITA` y `EN_RELACION_CON` para 3-4). Los **33 restantes** del catálogo (correcciones, recursos TC, anulaciones, etc.) **se ignoran** — no contribuyen a las preguntas del Consejo.

#### 2.3 Preprocesado en orden antiguo → nuevo

```python
# src/preproc/runner.py
def preprocesar_todo() -> None:
    años = sorted(Path("data_api/raw").iterdir())                # 1887, 1888, ...
    for año_dir in años:
        ficheros = sorted(año_dir.glob("*.xml"))                  # orden alfabético = orden de publicación
        for f in ficheros:
            norma = parser.parse_xml(f, flags=settings.parse_flags)
            store.upsert_norma(norma)
            for ref in norma.referencias_anteriores:
                if ref.codigo in settings.relacion.codigos_a_relacion:
                    rel_type = settings.relacion.codigos_a_relacion[ref.codigo]
                    store.upsert_relacion(norma.id, rel_type, ref.id_norma, texto=ref.texto)
```

Si una arista intenta apuntar a un `id_norma` aún no insertado (por estar en un año posterior), se crea el nodo como **placeholder** con solo `id` y se completará cuando llegue su fichero. Eso evita romper la carga aunque el orden no sea perfecto.

#### 2.4 Esquemas en `data/ontology/` (Markdown + JSON)

El prompt pide **emitir el esquema** de la capa semántica y la dinámica. Se generan tras el preprocesado, no son leídos por la app — son documentación viva:

```
data/ontology/
├── semantic-layer/
│   ├── node.norma.md          # tabla con todos los atributos (los que tienen True en ParseFlags)
│   ├── node.norma.schema.json # JSON Schema
│   ├── edge.deroga.md         # uno por cada verbo materializado
│   ├── edge.modifica.md
│   ├── edge.cita.md
│   ├── ...
│   └── edges.schema.json      # esquema agregado
└── dynamic-layer/
    ├── node.query_usuario.md
    ├── node.query_usuario.schema.json
    └── edge.responde_edge.md
```

Cada `.md` lista: nombre, descripción, tipo, obligatorio, ejemplo. Generado por `src/graph/ontology.py:dump_schemas()` a partir de los Pydantic models — fuente única de verdad.

#### 2.5 Ontología A (flat) — la que se usa

Un único tipo de nodo `:Norma` con todos los atributos parseados, aristas etiquetadas por el `relacion.codigo` traducido a TYPE Cypher.

```cypher
(n:Norma {
  id: "BOE-A-2015-10565",
  titulo: "...",
  rango_codigo: 1300, rango_texto: "Ley",
  fecha_publicacion: date("2015-10-02"),
  vigente: true,            // computado: estatus_derogacion='N' AND estatus_anulacion='N' AND vigencia_agotada='N'
  ...
})
-[:DEROGA {codigo: 210, texto: "los arts. 4 a 7 de la Ley 2/2011..."}]->
(:Norma {id: "BOE-A-2011-4117"})
```

#### 2.6 Capa dinámica — interacción usuario ↔ ontología

```cypher
(q:QueryUsuario {
  id: "uuid-v7",
  prompt: "¿Qué leyes dependen de la Ley 30/1992?",
  respuesta: "Las siguientes leyes vivas la citan...",
  ts: datetime()
})
-[:RESPONDE_EDGE {id_query_usuario: "uuid-v7", id_nodo: "BOE-A-2015-10565"}]->
(:Norma {id: "BOE-A-2015-10565"})
```

Cada consulta del usuario crea:
1. **1 nodo `:QueryUsuario`** con `id` (UUIDv7 — ordenable por tiempo), `prompt`, `respuesta`, `ts`.
2. **N aristas `:RESPONDE_EDGE`** con atributos `id_query_usuario` e `id_nodo` (redundantes con el endpoint pero útiles para queries SIN traversal), una por cada norma citada en la respuesta del LLM.

Schemas en `data/ontology/dynamic-layer/node.query_usuario.md` y `edge.responde_edge.md`.

Estas relaciones se crean desde el endpoint `/api/chat` del backend tras recibir la respuesta de Claude. **Las aristas `:RESPONDE_EDGE` participan del grafo** que se renderiza en `/graph` (con el filtro `query_usuario` para mostrarlas u ocultarlas — ver §3.2).

#### 2.7 ¿rustworkx en v2?

**No.** En v1 lo justificaba el cálculo de PageRank y métricas globales del grafo derivado. En v2 no hay grafo derivado y los 4 briefings son Cypher puros. Para la visualización web, Sigma.js consume **JSON exportado desde Neo4j vía Cypher** (`MATCH (n)-[r]-(m) RETURN n,r,m`). No se necesita estructura en memoria de Python intermedia. **`rustworkx` queda fuera.**

#### 2.8 GDPR fuera

Decisión del prompt. La capa dinámica almacena prompts del usuario sin cifrado, sin TTL, sin opt-out. Aceptado para v2.

#### 2.9 Tests de preprocesado y carga Neo4j

Sin contenedores: para los tests de Neo4j el usuario debe tener una instancia local con una **base de datos `reversa_test` aparte** (Neo4j Community 5 soporta multi-DB). El fixture conecta a ella, ejecuta `MATCH (n) DETACH DELETE n` al inicio y al final.

**`tests/unit/preproc/`** (sin Neo4j):

| Test | Verifica |
|---|---|
| `test_parser_aplica_flags_true` | Solo se extraen los atributos con `True` |
| `test_parser_ignora_flags_false` | Atributos con `False` no aparecen en el modelo resultado |
| `test_parser_vigente_calculado_correctamente` | Combina derogación + anulación + vigencia_agotada → bool |
| `test_parser_ignora_referencias_posteriores` | `posteriores` no se parsea (flag False) |
| `test_parser_filtra_codigos_no_configurados` | Una `<anterior codigo=201>` (corrección) no genera arista |
| `test_parser_imagenes_base64_se_mantienen_en_xml_pero_no_en_modelo` | El parser no las parsea ni las pierde, simplemente las deja en el XML fuente |
| `test_orden_temporal_estable` | Ordenar 3 ficheros mezclados → mismo orden que `fecha_publicacion` |

**`tests/integration/graph/`** (con Neo4j local):

| Test | Verifica |
|---|---|
| `test_upsert_norma_idempotente` | Reingerir la misma norma no duplica nodo |
| `test_upsert_relacion_idempotente` | Reingerir la misma referencia no duplica arista |
| `test_briefing_1_top_modificadas` | Sobre fixture de 10 normas, el top 5 es el esperado |
| `test_briefing_2_top_modificadoras` | Idem para "omnibus" |
| `test_briefing_3_porcentaje_rot` | Cálculo de % vivas-citan-muertas |
| `test_briefing_4_blast_radius_30_1992` | Devuelve la lista esperada |
| `test_placeholder_se_completa_al_llegar_fichero` | Norma referenciada en t₁ y materializada en t₂ → nodo enriquecido |
| `test_query_usuario_y_responde_edge` | Crear `:QueryUsuario`, vincular aristas, recuperar por id |
| `test_dump_schemas_genera_md_y_json` | Tras carga, existen los ficheros en `data/ontology/` |

---

### 3. Frontend

#### 3.1 `/chat`

**Layout** (NiceGUI):

```
┌─────────────────────────────────────────────────────────┐
│  [🕸 Reversa]                                  [⚙]      │  ← header con icono de grafo enlazando a /graph
├─────────────────────────────────────────────────────────┤
│                                                         │
│              Bienvenido a Reversa!                      │  ← centrado, fuente grande
│                                                         │
│     ┌─────────────────────────────────────┐ ┌──────┐    │
│     │  Escribe tu pregunta...             │ │ →    │    │  ← textarea autoexpansiva + botón send
│     │                                     │ │      │    │
│     └─────────────────────────────────────┘ └──────┘    │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

Tras el primer envío, los mensajes empujan al input hacia abajo y la respuesta del LLM aparece en **streaming** (token a token):

```
┌─────────────────────────────────────────────────────────┐
│  Usuario: ¿Qué leyes dependen de la Ley 30/1992?       │
│                                                         │
│  Reversa: ▌                                             │  ← cursor de typewriter
│           Estas son las normas vivas que citan…        │
│           - BOE-A-2015-10565 — Ley 39/2015 …           │
│           - BOE-A-2015-10566 — Ley 40/2015 …           │
└─────────────────────────────────────────────────────────┘
```

**Sin uploads.** El `ui.textarea` de NiceGUI con `autogrow` y un botón `ui.button("→", on_click=send)` cubren el caso.

#### 3.2 LLM — Claude Haiku con system prompt

**Modelo**: `claude-haiku-4-5` (la última generación Haiku disponible). Razón: el chat no es generación libre sino **mapeo intención → query Cypher → respuesta narrativa con citas**. Haiku es 10× más barato que Sonnet y suficiente para esta tarea acotada.

**System prompt** (esqueleto):

```
Eres Reversa, un asistente jurídico especializado en el Boletín Oficial del Estado.

Tu única fuente de verdad es el grafo de conocimiento Neo4j local de Reversa,
que contiene 12 285 normas españolas consolidadas con sus relaciones:
DEROGA, MODIFICA, CITA, AÑADE, SUSTITUYE, SUPRIME, DESARROLLA, APRUEBA,
TRANSPONE, EN_RELACION_CON.

Cada norma tiene id (BOE-A-YYYY-NNNNN), titulo, rango, fecha_publicacion,
fecha_vigencia, vigente (bool).

Cuando el usuario te pregunte, decide qué consulta Cypher devuelve la respuesta
y la propones EN LENGUAJE NATURAL al usuario, junto con las normas relevantes
citadas en formato [BOE-A-YYYY-NNNNN — Título].

NO uses tools ni MCP. Si la pregunta es de las 4 estándar del Consejo,
responde con los 5 candidatos correspondientes:
1. Diagnóstico — top 5 más modificadas
2. Causa raíz — top 5 que más modifican
3. La podredumbre — % vivas citan muertas + top 5 fantasmas
4. El bisturí — blast radius de BOE-A-1992-26318 (Ley 30/1992)

NUNCA inventes IDs ni títulos. Si no tienes la información, dilo.
```

El backend (NiceGUI handler) **antes** de llamar a Claude:
1. Detecta keywords de las 4 briefings (regex/fuzzy) → ejecuta la Cypher correspondiente → inyecta el resultado en el contexto del usuario como `<resultado_grafo>`.
2. Llama a Claude con `stream=True` (`anthropic.messages.stream(...)`).
3. Cada token llega al frontend vía NiceGUI (`ui.markdown` + `.refresh()`).
4. Al terminar el stream, extrae los IDs citados en la respuesta del LLM, crea el nodo `:QueryUsuario` y las aristas `:RESPONDE_EDGE` en Neo4j (§2.6).

#### 3.3 Análisis del código del certificado (`src/llm/*.py`)

He revisado los 4 ficheros. Veredicto y plan de poda:

| Fichero | Tamaño | Función | Decisión v2 |
|---|---|---|---|
| `claude.py` | 78 líneas | Wrapper sobre `anthropic.Anthropic()`: añade mensajes al historial, extrae texto, parametriza `chat()` con system/temperature/tools/thinking | **CONSERVAR pero simplificar**. Quitar `tools` y `thinking` (el prompt prohíbe tools). Añadir un método `stream(messages, system)` que use `client.messages.stream(...)` para devolver un generador de tokens. |
| `chat.py` | 62 líneas | `Chat` class con bucle de tool-use: llama a Claude, si `stop_reason == "tool_use"` ejecuta tools MCP y reitera | **ELIMINAR el bucle de tool_use entero.** Simplificar a un `Chat` que solo acumule historial + llame a `Claude.stream()`. Sin `clients` ni `ToolManager`. |
| `cli.py` | 237 líneas | CLI con `prompt_toolkit`: autocompletado `/comandos` (prompts MCP), menciones `@docs` (resources MCP), atajos `/` y `@`, historial inline | **ELIMINAR completo.** No hay CLI, el frontend es NiceGUI. No hay MCP. |
| `cli_chat.py` | 173 líneas | Subclase de `Chat` que: extrae menciones `@doc` y carga el contenido como contexto XML; procesa comandos `/` invocando prompts MCP precargados; convierte `PromptMessage` de MCP a `MessageParam` de Anthropic | **ELIMINAR completo.** No hay uploads (sin `@doc`), no hay MCP (sin `/comandos`), no hay conversión MCP→Anthropic. |

**Lo que se conserva, depurado**:

```python
# src/llm/claude.py  (v2 — sin tools, sin thinking, con streaming)
from collections.abc import AsyncIterator
from anthropic import AsyncAnthropic
from anthropic.types import Message, MessageParam


class Claude:
    def __init__(self, model: str = "claude-haiku-4-5"):
        self.client = AsyncAnthropic()      # lee ANTHROPIC_API_KEY del entorno
        self.model = model

    def add_user_message(self, messages: list[MessageParam], text: str) -> None:
        messages.append({"role": "user", "content": text})

    def add_assistant_message(self, messages: list[MessageParam], text: str) -> None:
        messages.append({"role": "assistant", "content": text})

    async def stream(
        self,
        messages: list[MessageParam],
        system: str | None = None,
        max_tokens: int = 4000,
    ) -> AsyncIterator[str]:
        params: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system:
            params["system"] = system
        async with self.client.messages.stream(**params) as stream:
            async for text in stream.text_stream:
                yield text
```

```python
# src/llm/chat.py  (v2 — sin tools, sin MCP)
from anthropic.types import MessageParam
from reversa.llm.claude import Claude
from reversa.llm.system_prompt import SYSTEM_PROMPT


class Chat:
    def __init__(self, claude: Claude):
        self.claude = claude
        self.messages: list[MessageParam] = []

    async def run_stream(self, query: str):
        self.claude.add_user_message(self.messages, query)
        full = ""
        async for token in self.claude.stream(self.messages, system=SYSTEM_PROMPT):
            full += token
            yield token
        self.claude.add_assistant_message(self.messages, full)
```

**Lo que se elimina y por qué**:
- `prompt_toolkit` (CLI completo): redundante con NiceGUI.
- `MCPClient`, `ToolManager`, `mcp.types`: el prompt prohíbe tools y MCP.
- `@doc` mention parsing: no hay uploads.
- `/command` dispatch a prompts MCP: no hay sistema de prompts MCP.
- `convert_prompt_messages_to_message_params`: solo tenía sentido para MCP.
- `thinking` y `stop_sequences` en `claude.py`: no se usan en el chat de Reversa.
- Bucle `while True` con `stop_reason == "tool_use"`: sin tools, sin loop.

**Total eliminado**: ~410 líneas de código (cli.py + cli_chat.py + chat.py loop + tools en claude.py). Lo que queda son ~60 líneas útiles.

#### 3.4 `/graph`

**Layout**:

```
┌──────────────────────────────────────────────────────────────────────────┐
│  [🕸 Reversa]   [💬 Chat]                                                │
├──────────────┬──────────────────────────────────────┬────────────────────┤
│ Filtros      │                                      │ [✕] Info nodo      │
│              │                                      │ id: BOE-A-2015-… │
│ rango        │                                      │ titulo: Ley 39/…  │
│ [Ley___▾]    │           SIGMA.JS CANVAS            │ rango: Ley         │
│              │                                      │ vigente: ✔         │
│ vigente      │              [O]                     │ fecha_pub: …       │
│ [✔/✘]        │           /   |   \                  │ …                  │
│              │          O    O    O                 │                    │
│ fecha_pub    │           \   |   /                  │                    │
│ [2015]       │              [O]                     │                    │
│              │                                      │                    │
│ query_usu.   │      [zoom +] [zoom -]               │                    │
│ ◯ Todas      │                                      │                    │
│ ◯ Una        │                                      │                    │
│ ◯ Ninguna    │                                      │                    │
│              │                                      │                    │
│ [Reestab.]   │                                      │                    │
│ [Aplicar]    │                                      │                    │
└──────────────┴──────────────────────────────────────┴────────────────────┘
```

**Comportamiento**:
- Al cargar `/graph` sin parámetros → render del grafo entero (`MATCH (n)-[r]-(m) RETURN n,r,m`).
- **Zoom + pan + drag**: nativo de Sigma.js. Botones `+`/`-` y rueda del ratón.
- **Click en nodo** → emite evento al backend → backend devuelve atributos del nodo → panel derecho se abre con todos los datos. Botón **`✕` arriba a la izquierda** del panel para cerrar.
- **Click en arista** → mismo flujo: panel derecho muestra:
  - `accion`: TYPE de la relación (p.ej. `DEROGA`).
  - `nodo_activo`: id del nodo origen + título.
  - `nodo_pasivo`: id del nodo destino + título.
  - `texto`: el `texto` libre que precisa el alcance ("los arts. 4 a 7 de la Ley 2/2011").
- **Sidebar izquierdo de filtros** — siempre visible:
  - Un campo por **cada atributo del esquema** de `data/ontology/semantic-layer/node.norma.md` y de `dynamic-layer/node.query_usuario.md`.
  - Tipo de campo por atributo: `select` para enums (rango, ambito), `date-range` para fechas, `text` para títulos, `checkbox` para booleans (vigente).
  - Bloque "query_usuario" con tres modos:
    - **Todas** (por defecto): se muestran junto al resto.
    - **Una/Varias**: input de IDs concretos (`text` con autocomplete).
    - **Ninguna**: oculta `:QueryUsuario` y sus aristas.
  - Botones **`Reestablecer`** (izquierda) y **`Aplicar`** (derecha).
  - **URL sync**: cada filtro aplicado se serializa en query string `/graph?rango=1300&vigente=true&fecha_pub_desde=2015...&query_usuario=todas`. Compartible y bookmarkeable.

**Tecnología**:
- NiceGUI maneja layout (`ui.splitter`, `ui.row`, `ui.column`, `ui.expansion`), filtros (`ui.select`, `ui.date_input`, `ui.input`, `ui.button`), y URL state.
- Sigma.js se embebe vía un componente custom de NiceGUI que monta un `<div id="sigma-canvas">` con un puente JS de ~50 líneas en `src/web/static/sigma_bridge.js`:
  - Recibe `graph_data` (JSON con `{nodes:[{id,label,attrs}], edges:[{src,dst,type,attrs}]}`) desde Python vía `ui.run_javascript`.
  - Inicializa `graphology` + `Sigma` con `forceAtlas2` layout.
  - Escucha `clickNode` y `clickEdge` → llama de vuelta a Python con el id.

#### 3.5 ¿Lazy load o todo de golpe?

12 285 nodos + ~150 k aristas en JSON crudo son ~30 MB sobre la red. Sigma WebGL renderiza sobrado. **Carga inicial completa** — es lo más sencillo y cubre el requisito "inicialmente mostrar todo el grafo".

Si en algún momento se hace pesado (filtros muy específicos o despliegue a >100 k nodos), añadir backend-side filtering ya implementado vía la query Cypher parametrizada por filtros: solo se serializa el subgrafo resultado.

---

### 4. `src/` v2 — estructura final simplificada

```
src/
├── __init__.py
├── main.py                        # entry: arranca NiceGUI + FastAPI
├── config.py                      # ⭐ todas las config de cada clase (Pydantic Settings frozen)
│
├── api/                           # cliente HTTP del BOE
│   ├── __init__.py                # exporta: BOEClient, BOEDownloader, ResumenDescarga
│   ├── client.py                  # httpx sync — sin retries, sin rate limit, sin UA
│   ├── downloader.py              # descargar_masivo() / reintentar() / descargar_selectivo()
│   ├── errors.py                  # persistencia en data_api/errors/{id}.json
│   └── models.py                  # Pydantic: Norma (parsed), Referencia, ResumenDescarga
│
├── preproc/                       # XML → modelo Python
│   ├── __init__.py                # exporta: XMLParser, parse_xml
│   ├── parser.py                  # parsea aplicando ParseFlags de config.py
│   └── runner.py                  # itera data_api/raw/ en orden temporal, llama a graph.store
│
├── graph/                         # Neo4j + ontología
│   ├── __init__.py                # exporta: Neo4jStore, dump_schemas, briefings
│   ├── store.py                   # driver Neo4j: upsert_norma, upsert_relacion, upsert_query_usuario
│   ├── ontology.py                # modelos Pydantic de Norma/Edge/QueryUsuario/ResponderEdge + dump_schemas()
│   ├── briefings.py               # las 4 queries Cypher (top_modificadas, top_modificadoras, rot, blast_radius)
│   └── dynamic.py                 # upsert_query_usuario + responde_edges desde el chat backend
│
├── llm/                           # cliente Claude (depurado del certificado)
│   ├── __init__.py                # exporta: Claude, Chat
│   ├── claude.py                  # ~25 líneas — wrapper streaming, sin tools, sin thinking
│   ├── chat.py                    # ~20 líneas — historial + run_stream()
│   └── system_prompt.py           # SYSTEM_PROMPT centralizado
│
├── web/                           # NiceGUI
│   ├── __init__.py                # exporta: create_app
│   ├── app.py                     # FastAPI + NiceGUI mount, registro de rutas
│   ├── pages/
│   │   ├── __init__.py
│   │   ├── chat.py                # /  y /chat — bienvenida + textarea autogrow + send + streaming render
│   │   └── graph.py               # /graph — Sigma + filtros + panel info + URL sync
│   ├── components/
│   │   ├── __init__.py
│   │   ├── sigma_canvas.py        # wrapper NiceGUI alrededor de sigma_bridge.js
│   │   ├── filter_panel.py        # sidebar izq: auto-genera campos desde la ontología
│   │   └── info_panel.py          # sidebar dch: ✕ + datos de nodo/arista
│   └── static/
│       └── sigma_bridge.js        # ~50 líneas — bootstrap Sigma + click handlers
│
└── cli/                           # comandos typer
    ├── __init__.py                # exporta: app
    ├── api_cmd.py                 # reversa api {masivo|reintentar|selectivo}
    ├── preproc_cmd.py             # reversa preproc {ejecutar|esquemas}
    └── briefings_cmd.py           # reversa briefings {1|2|3|4|todos}
```

**Comparado con v1, se eliminan:**
- `config/` (carpeta) — reemplazado por `config.py` plano (decisión del prompt).
- `ingesta/` — fusionado en `api/`.
- `analytics/` (DuckDB) — fuera.
- `rag/` entero — fuera (sin RAG, sin embeddings, sin chunking, sin vector store).
- `memory/` — la capa dinámica vive ahora en `graph/dynamic.py`.
- `parsers/` — sin uploads.
- `observability/` — sin Prometheus/OpenTelemetry/Langfuse (overengineering para v2).
- `graph/store_inmem.py` (rustworkx) — fuera.
- `graph/derived.py` — fuera (sin doble grafo).
- `llm/router.py`, `llm/state.py`, `llm/ollama_client.py` — solo Anthropic Haiku, sin fallback.

**Exports principales (`__init__.py`):**

```python
# src/api/__init__.py
from .client import BOEClient
from .downloader import BOEDownloader, ResumenDescarga, ResumenReintento
from .errors import ErrorStore
from .models import Norma, Referencia
__all__ = ["BOEClient", "BOEDownloader", "ResumenDescarga", "ResumenReintento",
           "ErrorStore", "Norma", "Referencia"]
```

```python
# src/graph/__init__.py
from .store import Neo4jStore
from .ontology import NormaModel, EdgeModel, QueryUsuarioModel, ResponderEdgeModel, dump_schemas
from .briefings import (top_modificadas, top_modificadoras,
                        porcentaje_rot, top_muertas_citadas, blast_radius_30_1992)
from .dynamic import upsert_query_usuario
__all__ = ["Neo4jStore", "NormaModel", "EdgeModel", "QueryUsuarioModel",
           "ResponderEdgeModel", "dump_schemas", "top_modificadas",
           "top_modificadoras", "porcentaje_rot", "top_muertas_citadas",
           "blast_radius_30_1992", "upsert_query_usuario"]
```

```python
# src/llm/__init__.py
from .claude import Claude
from .chat import Chat
__all__ = ["Claude", "Chat"]
```

```python
# src/web/__init__.py
from .app import create_app
__all__ = ["create_app"]
```

**`src/config.py` (esqueleto):**

```python
"""Configuración centralizada de Reversa v2.

Una clase Settings por componente, todas frozen, cargadas desde .env al
arrancar. Importar con `from reversa.config import settings`.
"""

from __future__ import annotations

from pathlib import Path
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class APIConfig(BaseModel):
    base_url: str = "https://www.boe.es/datosabiertos/api"
    timeout_s: float = 30.0
    raw_dir: Path = Path("data_api/raw")
    errors_dir: Path = Path("data_api/errors")
    tests_dir: Path = Path("data_api/tests")
    ids_filename: str = "ids.txt"


class ParseFlags(BaseModel):
    # (ver §2.2 — un bool por atributo)
    identificador: bool = True
    titulo: bool = True
    # ... etc


class RelacionConfig(BaseModel):
    codigos_a_relacion: dict[int, str] = {
        210: "DEROGA", 211: "DEROGA_LO_INDICADO", 212: "DEROGA_CON_EXCEPCION",
        213: "DEROGA_EN_CUANTO_SE_OPONGA", 214: "DEROGA_EN_FORMA_INDICADA",
        215: "DEROGA_PARCIALMENTE", 216: "DEROGA_REITERADA", 217: "DEROGA_TACITAMENTE",
        270: "MODIFICA", 271: "MODIFICA_PLAN", 272: "MODIFICA_DET",
        235: "SUPRIME", 245: "SUSTITUYE", 407: "AÑADE",
        330: "CITA", 331: "EN_RELACION_CON",
        490: "DESARROLLA", 420: "APRUEBA",
        426: "TRANSPONE", 427: "TRANSPONE_PARCIALMENTE",
    }


class Neo4jConfig(BaseModel):
    uri: str = "bolt://localhost:7687"
    user: str = "neo4j"
    password: str = ""           # cargado de env
    database: str = "reversa"
    test_database: str = "reversa_test"


class LLMConfig(BaseModel):
    model: str = "claude-haiku-4-5"
    max_tokens: int = 4000
    api_key: str = ""            # cargado de env (ANTHROPIC_API_KEY)


class WebConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8080
    title: str = "Reversa"


class OntologyConfig(BaseModel):
    output_dir: Path = Path("data/ontology")
    semantic_subdir: str = "semantic-layer"
    dynamic_subdir: str = "dynamic-layer"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_nested_delimiter="__", frozen=True
    )
    api: APIConfig = APIConfig()
    parse: ParseFlags = ParseFlags()
    relacion: RelacionConfig = RelacionConfig()
    neo4j: Neo4jConfig = Neo4jConfig()
    llm: LLMConfig = LLMConfig()
    web: WebConfig = WebConfig()
    ontology: OntologyConfig = OntologyConfig()


settings = Settings()
```

**`src/main.py`:**

```python
"""Reversa entry point — arranca NiceGUI + FastAPI."""

from __future__ import annotations

from reversa.config import settings
from reversa.web import create_app


def main() -> None:
    app = create_app()
    # NiceGUI gestiona uvicorn internamente
    from nicegui import ui
    ui.run(host=settings.web.host, port=settings.web.port,
           title=settings.web.title, reload=False)


if __name__ == "__main__":
    main()
```

---

### 5. Resumen de simplificaciones v1 → v2

| Tema | v1 | v2 |
|---|---|---|
| Cliente HTTP | `httpx async` + `tenacity` + `aiolimiter` + `hishel` + UA + HTTP/2 | `httpx sync`, sin retries, sin rate limit, sin cache |
| Endpoints API | consolidada + sumarios + BORME + tablas auxiliares | **solo** `/legislacion-consolidada` (lista + `/id/{id}`) |
| Formato | JSON donde se pueda, XML para texto | **XML para todo** (`/id/{id}` lo devuelve unificado) |
| Imágenes/tablas | filtrar `<img>` base64 | **se guardan** todo |
| Almacenes | Neo4j + DuckDB + Qdrant + `.md` versionado con DVC | **solo Neo4j** + XML crudo en disco |
| Ontología | 3 propuestas, north-star "tres capas Palantir" | **A (flat)** + capa dinámica usuario |
| Doble grafo raw/derivado | sí, con materialized views | **fuera** |
| Algoritmos grafo en memoria | `rustworkx` | **fuera** (Cypher puro) |
| Chunking | jerárquico Libro/Título/Cap/Art + SAC | **fuera** |
| RAG | híbrido BGE-M3 + Qdrant + reranker + DSPy + LlamaIndex | **fuera** |
| Embeddings | BGE-M3 + posibles legal-domain ES | **fuera** |
| LLM | Claude (Sonnet/Opus) + fallback Ollama Qwen | **Claude Haiku** sin fallback |
| Tools/MCP | function calling con JSON schemas | **sin tools, sin MCP** |
| Frontend | NiceGUI + Sigma.js + Cytoscape como plan B | **NiceGUI + Sigma.js** (ipysigma) |
| File uploads | docling + 25 MB + AV | **sin uploads** |
| Streaming | Anthropic streaming | **mantenido** |
| Observabilidad | structlog + Prometheus + OpenTelemetry + Langfuse | **structlog mínimo** |
| Tests | unit + integration (testcontainers) + e2e (playwright) | unit + integration (Neo4j local) — **sin contenedores, sin Playwright** |
| Versionado datos | DVC | **fuera** |
| GDPR / TTL queries | sí, 90 días + cifrado | **fuera** |
| Referencias parseadas | `anteriores` + `posteriores` | **solo `anteriores`** (decisión del prompt) |
| Códigos materializados | los 53 | **20** (los que cubren los 4 briefings) |

---

### 6. Verificaciones pendientes (no bloqueantes)

1. **¿`/id/{id}` devuelve siempre `<metadata-eli>`?** El PDF lo lista como opcional `[0..1]`. Si está, lo dejamos en el XML pero no lo parseamos. Si no está, no es problema.
2. **Volumetría con texto completo** — bajar las ~12 285 normas con `<texto>` + base64 imágenes puede subir el corpus a ~1.3 GB. Confirmar que hay espacio antes del `descargar_masivo()`.
3. **Idioma de la UI de NiceGUI** — todo en español. Comprobar que los componentes nativos (date picker, select) respetan locale.
4. **Estimación de coste Claude Haiku** — para los flujos "el LLM mapea pregunta → narrativa con citas", suponiendo ~1000 tokens in / 500 out por turno y consumo de demo: <$0.01 por consulta. Negligible.
