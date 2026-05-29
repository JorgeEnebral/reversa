# Reversa — Plan arquitectónico v2 (1-vision-v2.md)

> v3 sobre [`vision-v2.md`]. Las decisiones aquí **sobrescriben** a las de v2; lo que no se mencione, se mantiene.

## Prompt

Partiendo de v3 que se han hecho algunas modificaciones a v2, actualiza v3 teniendo en cuenta la siguiente información
- No toques nada de la API, ya esta terminada.
- Para el preprocesado de datos raw xml se crea el fichero preprocess.py. En config.py hay que poner qué atributos parsear (metadatos, analisis, metadatos-eli, texto) [true, false] y dentro de cada uno todos sus atributos también para preprocesarlos si son true y su categoria padre lo es (no pongas ningun tag para metadatos-eli ni texto, solo deja la estructura para un futuro).
- A partir de los esquemas al inicio se borran todos los esquemas de data/ontology/semantic-layer y se crean de nuevo. Diferencia entre el .md y el schema.json que se pone en v3. Los de la capa dinamica los escribe el usuario.
- Se tienen que guardar los datos en el momento que se preprocesan en neo4j. es un entorno de wsl. di pasos para descargar o lo que se necesite.
- No poner tests de neo4j por simplicidad y no tener que duplicar. Solo la bbdd de produccion en disco. Los tests estarán en tests/test_preprocess.py
- No toques nada del plan edl frontend
- Unifica en una clase Claude, Chat y prompt, para que sea solo un fichero llm.py dentro de src/. Las variables secreto di cuales son y como ponerlas en .env. Porque usar asyn Anthropic y no Anthropic()< Poder poner temperatura, max tokens, lista maxima de 10 mensajes: 5 usuario y 5 asistente, a partir de ahi los primeros se olvidan

---

## Librerías a descargar manualmente con uv

> Ejecutar **en orden, paso a paso**. Cada bloque corresponde a un hito del plan; no instalar todo de golpe.

```bash
# --- Hito 1: API (descarga masiva) ---
uv add httpx lxml pydantic pydantic-settings python-dotenv typer structlog

# --- Hito 2: Preprocesado + Neo4j ---
uv add neo4j lxml  # lxml ya está, neo4j es el driver oficial Python

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
- **Sin contenedores**: Neo4j Community se instala **nativamente en WSL** (ver §2.0). Una sola base de datos en producción (en disco). **No hay base de datos de tests** — los tests de preprocesado no tocan Neo4j (ver §2.7).

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

#### 2.0 Instalación de Neo4j en WSL (Ubuntu)

Una sola instancia, una sola base de datos en disco (`reversa`). Sin contenedores, sin tests sobre Neo4j.

```bash
# 1. Java 21 (Neo4j 5 lo requiere)
sudo apt update
sudo apt install -y openjdk-21-jre-headless

# 2. Repo oficial de Neo4j
sudo mkdir -p /etc/apt/keyrings
wget -qO - https://debian.neo4j.com/neotechnology.gpg.key \
  | sudo gpg --dearmor -o /etc/apt/keyrings/neotechnology.gpg
echo 'deb [signed-by=/etc/apt/keyrings/neotechnology.gpg] https://debian.neo4j.com stable 5' \
  | sudo tee /etc/apt/sources.list.d/neo4j.list

# 3. Instalar Neo4j Community 5
sudo apt update
sudo apt install -y neo4j

# 4. Contraseña inicial (sustituir <PASSWORD>)
sudo neo4j-admin dbms set-initial-password '<PASSWORD>'

# 5. Arrancar (en WSL no hay systemd por defecto; usar el servicio directo)
sudo service neo4j start
sudo service neo4j status     # debe mostrar "running"

# 6. Comprobar acceso
#    HTTP browser: http://localhost:7474  (usuario neo4j / contraseña anterior)
#    Bolt:         bolt://localhost:7687
```

**`.env`** del proyecto:

```
NEO4J__URI=bolt://localhost:7687
NEO4J__USER=neo4j
NEO4J__PASSWORD=<la contraseña que pusiste arriba>
NEO4J__DATABASE=reversa
```

> Pydantic Settings lee estas claves con prefijo `NEO4J__` gracias a `env_nested_delimiter="__"` (§4). `os.environ["NEO4J__PASSWORD"]` (no `os.getenv`) hace que la app falle ruidosamente si falta el secreto, según las reglas de seguridad.

Crear la base de datos `reversa` una sola vez desde Cypher Shell o el browser:

```cypher
CREATE DATABASE reversa IF NOT EXISTS;
```

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

#### 2.2 Parseado XML dirigido por `config.py`

Cuatro bloques raíz, idénticos a los del XML del BOE: `<metadatos>`, `<analisis>`, `<metadata-eli>`, `<texto>`. Cada bloque es un flag booleano o un sub-modelo con un `bool` por atributo. Regla evaluada en cascada: **si el padre es `False` o es un sub-modelo con `bool=False`, el bloque entero se omite**. Si el padre está activo, sólo se parsean los hijos con `True`.

`metadata-eli` y `texto` se dejan **con la estructura preparada pero vacía** — sin atributos por ahora — porque ningún briefing los necesita. Quedan reservados para futuras versiones.

```python
# src/config.py — flags de parseo

class MetadatosFlags(BaseModel):
    """Atributos de <metadatos>. Cada True extrae ese campo al modelo Norma."""
    identificador: bool = True
    titulo: bool = True
    diario: bool = True
    departamento: bool = True
    rango: bool = True            # codigo + texto
    fecha_disposicion: bool = True
    fecha_publicacion: bool = True
    fecha_vigencia: bool = True
    fecha_derogacion: bool = False
    numero_oficial: bool = False
    estatus_derogacion: bool = True   # alimenta `vigente`
    estatus_anulacion: bool = True    # alimenta `vigente`
    vigencia_agotada: bool = True     # alimenta `vigente`
    estado_consolidacion: bool = False
    judicialmente_anulada: bool = False
    url_eli: bool = False
    url_epub: bool = False
    url_pdf: bool = False


class AnalisisFlags(BaseModel):
    """Atributos de <analisis>. Sólo `referencias_anteriores` alimenta aristas."""
    materias: bool = True
    alertas: bool = False
    notas: bool = False
    observaciones: bool = False
    referencias_anteriores: bool = True
    referencias_posteriores: bool = False  # redundantes con anteriores del otro lado


class MetadataEliFlags(BaseModel):
    """Atributos de <metadata-eli>. Estructura reservada — sin campos por ahora."""
    pass


class TextoFlags(BaseModel):
    """Atributos de <texto>. Estructura reservada — sin campos por ahora."""
    pass


class ParseFlags(BaseModel):
    """Controla el parseado. Si un bloque raíz es False, se ignora entero.

    Si es un sub-modelo, sólo se evalúan sus hijos con True.
    """
    metadatos: MetadatosFlags | bool = MetadatosFlags()
    analisis: AnalisisFlags | bool = AnalisisFlags()
    metadata_eli: MetadataEliFlags | bool = False    # reservado
    texto: TextoFlags | bool = False                 # reservado
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

#### 2.3 Preprocesado escribe **directamente** a Neo4j

`src/preprocess.py` recorre `data/api/raw/{YYYY}/*.xml` en orden temporal y, para cada norma, **persiste el nodo y sus aristas en Neo4j en la misma iteración** — no hay representación intermedia en disco más allá del XML original. La fuente de verdad es el grafo.

```python
# src/preprocess.py
from pathlib import Path
from neo4j import GraphDatabase
from src.config import settings


class Preprocesador:
    """Parsea XML del BOE y escribe nodos/aristas en Neo4j directamente."""

    def __init__(self) -> None:
        self._driver = GraphDatabase.driver(
            settings.neo4j.uri,
            auth=(settings.neo4j.user, settings.neo4j.password),
        )
        self._db = settings.neo4j.database

    def preprocesar_todo(self) -> ResumenPreproc:
        años = sorted(Path("data/api/raw").iterdir())
        with self._driver.session(database=self._db) as s:
            for año_dir in años:
                for f in sorted(año_dir.glob("*.xml")):       # orden alfabético = ID = publicación
                    norma = parse_xml(f, flags=settings.parse)
                    self._upsert_norma(s, norma)
                    for ref in norma.referencias_anteriores:
                        rel = settings.relacion.codigos_a_relacion.get(ref.codigo)
                        if rel:
                            self._upsert_relacion(s, norma.id, rel, ref.id_norma, ref.texto)
        # Tras carga: regenerar esquemas semánticos (§2.4)
        regenerar_esquemas_semanticos()
        return ResumenPreproc(...)
```

**Idempotencia** — todo es `MERGE`, no `CREATE`:

```cypher
MERGE (n:Norma {id: $id})
SET n += $props
```

```cypher
MERGE (a:Norma {id: $src})
MERGE (b:Norma {id: $dst})
MERGE (a)-[r:DEROGA {codigo: $codigo}]->(b)
SET r.texto = $texto
```

`MERGE` sobre `:Norma {id}` crea **placeholders** automáticamente si la norma destino aún no se ha procesado. Cuando más adelante llega su XML, el `MERGE` la encuentra y el `SET n += $props` la enriquece. No hace falta lógica explícita de placeholders.

**Tipo de relación dinámico**: Cypher no permite parametrizar el TYPE; o se usa APOC (`apoc.merge.relationship`) o se construye la query con f-string contra una whitelist (`settings.relacion.codigos_a_relacion.values()` ya está validada en config). Se elige f-string + whitelist para no depender de APOC.

#### 2.4 Esquemas en `data/ontology/` (Markdown + JSON)

**Capa semántica**: se **borra y regenera por completo al inicio de cada preprocesado**. Es documentación derivada — fuente única de verdad: los `ParseFlags` activos + el catálogo `codigos_a_relacion`. Nunca se edita a mano.

**Capa dinámica**: la escribe el usuario a mano (ver §2.6). El preprocesado **no la toca**.

```
data/ontology/
├── semantic-layer/                ← regenerado en cada preprocesado
│   ├── nodes/
│   │   ├── node.norma.md
│   │   └── node.norma.schema.json
│   └── edges/
│       ├── deroga.md
│       ├── deroga.schema.json
│       ├── modifica.md
│       ├── modifica.schema.json
│       ├── cita.md
│       ├── cita.schema.json
│       └── ...                    ← uno por cada TYPE materializado en codigos_a_relacion
└── dynamic-layer/                 ← escrito a mano por el usuario, NUNCA se sobrescribe
    ├── nodes/
    │   ├── node.query_usuario.md
    │   └── node.query_usuario.schema.json
    └── edges/
        ├── responde_edge.md
        └── responde_edge.schema.json
```

**Diferencia `.md` vs `.schema.json`** (los dos son obligatorios y cada uno tiene un consumidor distinto):

| Fichero | Audiencia | Contenido | Generado desde |
|---|---|---|---|
| `*.md` | Humanos (revisión, PRs, onboarding) | Tabla legible: nombre, tipo, obligatorio, descripción, ejemplo, restricciones | El mismo `BaseModel` de Pydantic + descripciones (`Field(..., description=...)`) |
| `*.schema.json` | Máquinas (validación, generadores de cliente, futuros tools) | [JSON Schema Draft 2020-12](https://json-schema.org/draft/2020-12) con `$schema`, `type`, `properties`, `required`, `enum`, etc. | `Modelo.model_json_schema()` de Pydantic — una línea |

Ejemplo de cabecera `node.norma.md`:

```markdown
# :Norma

Nodo principal del grafo. Una norma consolidada del BOE.

| Atributo | Tipo | Obligatorio | Descripción | Ejemplo |
|---|---|---|---|---|
| id | string | sí | Identificador BOE | `BOE-A-2015-10565` |
| titulo | string | sí | Título oficial | `Ley 39/2015...` |
| rango_codigo | int | sí | Código de rango (1300=Ley...) | `1300` |
| vigente | bool | sí | Computado: derogación∧anulación∧vigencia_agotada=='N' | `true` |
...
```

Borrado-y-regeneración al arrancar `preprocesar_todo()`:

```python
def regenerar_esquemas_semanticos() -> None:
    sem = settings.ontology.output_dir / settings.ontology.semantic_subdir
    if sem.exists():
        shutil.rmtree(sem)
    (sem / "nodes").mkdir(parents=True)
    (sem / "edges").mkdir(parents=True)

    # Nodo Norma (sólo atributos con flag True)
    (sem / "nodes/node.norma.md").write_text(render_md_norma(settings.parse))
    (sem / "nodes/node.norma.schema.json").write_text(
        json.dumps(NormaSchema.model_json_schema(), ensure_ascii=False, indent=2)
    )

    # Una arista por cada TYPE materializado
    for codigo, rel_type in settings.relacion.codigos_a_relacion.items():
        nombre = rel_type.lower()
        (sem / f"edges/{nombre}.md").write_text(render_md_edge(rel_type, codigo))
        (sem / f"edges/{nombre}.schema.json").write_text(
            json.dumps(EdgeSchema.model_json_schema(), ensure_ascii=False, indent=2)
        )
```

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

Los esquemas (`*.md` y `*.schema.json`) los **escribe el usuario a mano** en `data/ontology/dynamic-layer/{nodes,edges}/`. El preprocesado nunca los toca y no los regenera. La razón: la dinámica refleja decisiones de producto (qué guardamos de cada conversación) que no se derivan del XML del BOE.
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
1. **1 nodo `:user_query`** con `id` (UUIDv7 — ordenable por tiempo), `prompt`, `respuesta`, `ts`.
2. **N aristas `:responde_edge`** con atributos `id_query_usuario` e `id_nodo` (redundantes con el endpoint pero útiles para queries SIN traversal), una por cada norma citada en la respuesta del LLM.

Schemas en `data/ontology/dynamic-layer/node.query_usuario.md` y `edge.responde_edge.md`.

Estas relaciones se crean desde el endpoint `/api/chat` del backend tras recibir la respuesta de Claude. **Las aristas `:RESPONDE_EDGE` participan del grafo** que se renderiza en `/graph` (con el filtro `query_usuario` para mostrarlas u ocultarlas — ver §3.2).


#### 2.7 Tests de preprocesado

**Decisión**: sin tests sobre Neo4j. La instancia de Neo4j es **una sola, la de producción**, en disco. Duplicarla con una DB de tests añade complejidad (gestión de credenciales en CI, limpieza, fixtures de carga) sin cubrir nada que no cubra ya un test sobre el parser. Las queries Cypher de los 4 briefings se validan a mano contra el grafo real cuando hace falta.

**Todos los tests del preprocesado viven en un único fichero: `tests/test_preprocess.py`.** Sin estructura `unit/integration` — la API ya marcó la convención (ver `tests/tests_api/test_downloader.py`).

| Test | Verifica |
|---|---|
| `test_parser_aplica_flags_true` | Sólo se extraen los atributos con `True` en `ParseFlags` |
| `test_parser_ignora_flags_false` | Atributos con `False` no aparecen en el modelo resultado |
| `test_parser_bloque_padre_false_ignora_hijos` | `metadatos=False` (bool) descarta el bloque entero |
| `test_parser_vigente_calculado_correctamente` | Combina derogación + anulación + vigencia_agotada → `bool` |
| `test_parser_ignora_referencias_posteriores` | `posteriores` no se parsea (flag False) |
| `test_parser_filtra_codigos_no_configurados` | Una `<anterior codigo=201>` (corrección) no genera arista |
| `test_orden_temporal_estable` | Ordenar 3 ficheros mezclados → mismo orden que `fecha_publicacion` |
| `test_regenerar_esquemas_borra_y_recrea_semantic_layer` | Tras llamada, `semantic-layer/` contiene `node.norma.md`, `node.norma.schema.json` y un par `{rel}.md`+`.schema.json` por cada TYPE en `codigos_a_relacion` |
| `test_regenerar_esquemas_no_toca_dynamic_layer` | Ficheros en `dynamic-layer/` preexistentes siguen intactos |
| `test_neo4j_driver_se_instancia_con_config` | Mock del driver; el parser respeta `settings.neo4j.uri/user/database` |

Los tests parsean XMLs de fixture en `tests/fixtures/xml/` y **mockean el driver de Neo4j** con `pytest-mock` (patch en el import site `src.preprocess.GraphDatabase`). Cero conexiones reales.

```python
def test_preprocesar_escribe_norma_con_merge(
    mocker: pytest.MockerFixture, fixture_xml: Path
) -> None:
    session = mocker.MagicMock()
    driver = mocker.MagicMock()
    driver.session.return_value.__enter__.return_value = session
    mocker.patch("src.preprocess.GraphDatabase.driver", return_value=driver)

    Preprocesador().preprocesar_todo()

    # Comprueba que la primera query es un MERGE sobre :Norma
    assert any("MERGE (n:Norma" in call.args[0] for call in session.run.call_args_list)
```

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

#### 3.3 LLM unificado — `src/llm.py` (una sola clase)

Toda la lógica de cliente Anthropic + historial conversacional + system prompt vive en **un único fichero `src/llm.py` con una única clase `Llm`**. Sin paquete `src/llm/`, sin `claude.py`/`chat.py`/`system_prompt.py` separados — el chat de Reversa es lo bastante simple para que la separación añada ruido sin valor.

**Secretos en `.env`** (el resto de config viaja en `src/config.py`):

```
ANTHROPIC_API_KEY=sk-ant-api03-...
```

Carga: `os.environ["ANTHROPIC_API_KEY"]` (loud-fail si falta, según [security.md](../.claude/rules/security.md)). `.env` está en `.gitignore`; `.env.example` se commitea con los nombres pero sin valores.

**¿Por qué `AsyncAnthropic` y no `Anthropic`?**
- NiceGUI corre sobre **uvicorn/asyncio**. Sus handlers son corrutinas.
- La respuesta del LLM se renderiza **en streaming token-a-token** (§3.2). El frontend necesita `yield` cooperativo al event loop entre tokens para refrescar el `ui.markdown` sin congelar el resto de la UI (clicks, otros usuarios, websockets).
- Con `Anthropic` sync, cada token bloquea el thread principal del event loop hasta volver; la solución sería envolverlo en `asyncio.to_thread(...)`, que es exactamente lo que `AsyncAnthropic` hace internamente pero ya integrado con el iterador asíncrono del SDK (`async with client.messages.stream(...) as s: async for tok in s.text_stream`).
- Coste cero: ambos clientes leen `ANTHROPIC_API_KEY` del entorno, comparten la API.

**Ventana deslizante de 10 mensajes (5 usuario + 5 asistente)** — los más antiguos se olvidan. La razón: el chat de Reversa es transaccional (pregunta → respuesta con citas); no hay sesiones largas que justifiquen pagar contexto cada turno. Cuando se inserta el mensaje 11.º, se descarta el más antiguo del **mismo rol** para preservar el patrón alternado `user/assistant/user/...` que la API exige.

**Parámetros configurables**: `temperature` y `max_tokens` por defecto vienen de `settings.llm` (ver §4); también se pueden sobreescribir por llamada.

```python
# src/llm.py
"""
Cliente LLM unificado de Reversa.

Una sola clase `Llm` que envuelve AsyncAnthropic, mantiene un historial
deslizante de 10 mensajes (5 user + 5 assistant) y expone un único método
de streaming.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from anthropic import AsyncAnthropic
from anthropic.types import MessageParam

from src.config import settings


SYSTEM_PROMPT = """\
Eres Reversa, un asistente jurídico especializado en el BOE.
... (idéntico al §3.2)
"""


@dataclass
class Llm:
    """Cliente de chat con Claude. Historial deslizante de 10 mensajes.

    Args:
        model: ID del modelo. Default: settings.llm.model.
        max_tokens: tokens máximos de salida por turno.
        temperature: 0.0 = determinista, 1.0 = creativo.
        system_prompt: instrucciones de sistema (no consume del historial).

    Attributes:
        messages: historial actual (máx 10).
    """

    model: str = field(default_factory=lambda: settings.llm.model)
    max_tokens: int = field(default_factory=lambda: settings.llm.max_tokens)
    temperature: float = field(default_factory=lambda: settings.llm.temperature)
    system_prompt: str = SYSTEM_PROMPT
    messages: list[MessageParam] = field(default_factory=list)

    _MAX_HISTORY = 10  # 5 user + 5 assistant

    def __post_init__(self) -> None:
        # Loud-fail si falta el secreto (security.md)
        os.environ["ANTHROPIC_API_KEY"]
        self._client = AsyncAnthropic()

    async def stream(self, user_text: str) -> AsyncIterator[str]:
        """Envía `user_text`, hace stream de la respuesta token a token.

        Yields:
            Cada delta de texto recibido del servidor.
        """
        self._push("user", user_text)
        full = ""
        async with self._client.messages.stream(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            system=self.system_prompt,
            messages=self.messages,
        ) as s:
            async for token in s.text_stream:
                full += token
                yield token
        self._push("assistant", full)

    def reset(self) -> None:
        """Borra el historial. El system prompt persiste."""
        self.messages.clear()

    def _push(self, role: str, content: str) -> None:
        self.messages.append({"role": role, "content": content})
        if len(self.messages) > self._MAX_HISTORY:
            # Descarta el mensaje más antiguo del mismo rol que el nuevo,
            # para preservar la alternancia user/assistant exigida por la API.
            for i, m in enumerate(self.messages[:-1]):
                if m["role"] == role:
                    del self.messages[i]
                    break
```

`LLMConfig` en `src/config.py` añade `temperature: float = 0.2`.

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
├── api.py
├── preprocess.py
│
├── llm.py
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
    temperature: float = 0.2
    # ANTHROPIC_API_KEY se lee directamente con os.environ[...] en src/llm.py
    # (no aquí, para no exponerla en el objeto Settings serializable)


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

### 5. Verificaciones pendientes (no bloqueantes)

1. **Idioma de la UI de NiceGUI** — todo en español. Comprobar que los componentes nativos (date picker, select) respetan locale.
2. **Estimación de coste Claude Haiku** — para los flujos "el LLM mapea pregunta → narrativa con citas", suponiendo ~1000 tokens in / 500 out por turno y consumo de demo: <$0.01 por consulta. Negligible.
