# Plan: Esquemas Pydantic como única fuente de verdad del render (`semantic_schemas.py` v2)

> Iteración sobre `plans/schemas.md`. Aquel plan **aisló** los esquemas en un módulo
> (`src/semantic_schemas.py`). Este plan elimina la **doble fuente de verdad** que quedó
> dentro de ese módulo: hoy los esquemas Pydantic conviven con tablas y renderers
> hardcodeados que repiten la misma información.

---

## 1. Contexto y problema

`src/semantic_schemas.py` define los 4 esquemas como `BaseModel`:

- `NormaSchema` (nodo `:Norma`)
- `EdgeSchema` (aristas semánticas `DEROGA`/`MODIFICA`/`CITA`)
- `UserQuerySchema` (nodo dinámico `:UserQuery`)
- `ResultEdgeSchema` (arista dinámica `:RESULT_EDGE`)

**Pero el render NO usa esos esquemas.** Cada campo está descrito **dos o tres veces**:

| Dónde | Qué contiene | Ejemplo |
|---|---|---|
| `NormaSchema` (BaseModel) | nombre, tipo, descripción | `ambito: str \| None = Field(None, description="Texto del ámbito territorial")` |
| `_NORMA_MD_FIELDS` / `_ANALISIS_MD_FIELDS` (tuplas) | flag, campo, tipo, oblig, descripción, ejemplo | `("ambito", "ambito", "string", "no", "Texto del ámbito territorial", "`Estatal`")` |
| `render_json_norma` / `render_json_edge` / ... | properties hardcodeadas + example | bloque `dict` escrito a mano por cada esquema |

Consecuencia: **añadir o cambiar un campo obliga a tocar 2–3 sitios** y a mantenerlos
sincronizados a mano. Ya hay deriva real:

- `render_json_norma` (código actual) **no** emite `vigente`, pero el `norma.json`/`norma.md`
  committeados **sí** lo tienen → fueron generados por una versión anterior.
- Tests como `test_render_md_norma_vigente_si_estatus_activos` esperan lógica de `vigente`
  que ya **no existe** en `render_md_norma`.
- `test_generar_esquemas_user_query_json_valido` asierta `type`/`additionalProperties` en la
  **raíz**, pero el código actual ya envuelve eso dentro de `input_schema` → test desincronizado.

## 2. Objetivo

Una sola tubería, una sola fuente:

```
  NormaSchema / EdgeSchema / UserQuerySchema / ResultEdgeSchema   (ÚNICA fuente)
        │  .model_json_schema()
        ▼
  JSON formato Anthropic   (name, description, input_schema{type,properties,required}, example)
        │  (se escribe en agents/*.json)
        ▼
  Markdown para humanos     (se escribe en humans/*.md)   ← se genera DESDE el JSON, no aparte
```

Reglas de diseño que fija el usuario:

1. Los 4 esquemas son la **única fuente de verdad**: contienen **todas** las variables, su
   **descripción**, **ejemplo** y algunos **valores por defecto**.
2. **No aceptan variables nuevas** → `model_config = ConfigDict(extra="forbid")` en los 4
   (hoy solo lo tienen `UserQuerySchema` y `ResultEdgeSchema`).
3. El JSON se obtiene de `.model_json_schema()` **reorganizado** al formato Anthropic.
4. El `.md` se genera **a partir del JSON** (no se mantiene por separado → cero doble trabajo).
5. El render debe ser **genérico** para los 4 esquemas (hoy está hardcodeado por tipo).

**Decisión confirmada (ejemplos):** se conserva la **columna `Ejemplo` por campo** en el `.md`.
Cada `Field` lleva `examples=[...]`; ese ejemplo viaja a cada *property* del JSON y la columna
del `.md` se rellena desde ahí. El `example` agregado del final del JSON se construye
**automáticamente** a partir de los `examples` de cada campo (sin mantenerlo a mano).

---

## 3. Formato Anthropic de salida (objetivo por esquema)

```jsonc
{
  "name": "Norma",
  "description": "Nodo principal del grafo. Una norma consolidada del boletín oficial.",
  "input_schema": {
    "type": "object",
    "properties": {
      "id":     { "type": "string",  "description": "Identificador BOE" },
      "user_id":{ "type": "string",  "description": "Id usuario", "default": "unknown" },
      "materias_codigos": { "type": "array", "items": {"type": "integer"}, "description": "..." }
    },
    "required": ["id"],
    "additionalProperties": false
  },
  "example": { "id": "BOE-A-2015-10565", "user_id": "unknown", "materias_codigos": [1270, 1680] }
}
```

Orden de claves dentro de cada *property*: `type` → `items?` → `description` → `default?` → `examples?`.

---

## 4. El reto técnico: `model_json_schema()` → formato Anthropic

`model_json_schema()` **no** sale limpio. Para un `str | None = Field(None, ...)` produce:

```jsonc
"fecha_actualizacion": {
  "anyOf": [{"type": "string"}, {"type": "null"}],
  "default": null,
  "title": "Fecha Actualizacion",          // basura: pydantic autogenera title
  "description": "Fecha de última actualización ISO-8601"
}
```

La transformación genérica debe, por cada property:

1. **Colapsar `anyOf [tipo, null]`** → quedarse con la rama no-null (`{type}` o `{type:"array", items}`).
2. **Eliminar `title`** (autogenerado por pydantic, no aporta).
3. **Eliminar `default: null`** (no es un default real; solo señala "opcional").
   Conservar defaults reales (`"unknown"`).
4. **Conservar** `description`, `examples`, e `items` (si array).
5. **Eliminar claves internas** que metamos para control de render (ver `x_flags` en §6).

### 4.1 Funciones nuevas (núcleo genérico)

```python
_JSON_TO_MD_TYPE: dict[str, str] = {
    "string": "string", "integer": "int", "boolean": "bool", "number": "float",
}

def _collapse_optional(prop: dict[str, Any]) -> dict[str, Any]:
    """Devuelve la rama no-null de un anyOf, o la prop tal cual si ya tiene type."""
    if "anyOf" in prop:
        return next(b for b in prop["anyOf"] if b.get("type") != "null")
    return prop

def _clean_prop(raw: dict[str, Any]) -> dict[str, Any]:
    """Property de model_json_schema() → property formato Anthropic (orden fijo)."""
    branch = _collapse_optional(raw)
    out: dict[str, Any] = {"type": branch["type"]}
    if branch["type"] == "array":
        out["items"] = branch["items"]
    out["description"] = raw["description"]
    if raw.get("default") is not None:      # descarta el default: null de los Optional
        out["default"] = raw["default"]
    if "examples" in raw:
        out["examples"] = raw["examples"]
    return out

def schema_to_anthropic(
    model: type[BaseModel],
    *,
    name: str,
    description: str,
    include: Callable[[str], bool] | None = None,
) -> dict[str, Any]:
    """Convierte un BaseModel al dict formato Anthropic.

    Args:
        model: esquema fuente.
        name: nombre del nodo/arista (e.g. "Norma", "DEROGA").
        description: descripción de una línea del tipo.
        include: filtro opcional por nombre de campo (Norma usa flags; el resto None).
    """
    raw = model.model_json_schema()
    req_src = set(raw.get("required", []))
    properties: dict[str, Any] = {}
    required: list[str] = []
    for field, prop in raw["properties"].items():
        if include is not None and not include(field):
            continue
        properties[field] = _clean_prop(prop)
        if field in req_src:
            required.append(field)

    input_schema: dict[str, Any] = {
        "type": "object", "properties": properties, "required": required,
    }
    if raw.get("additionalProperties") is False:      # extra="forbid"
        input_schema["additionalProperties"] = False

    example = {
        f: p["examples"][0] for f, p in properties.items() if "examples" in p
    }
    return {"name": name, "description": description,
            "input_schema": input_schema, "example": example}
```

### 4.2 MD genérico (consume el dict Anthropic, **no** el esquema)

```python
def _md_type(prop: dict[str, Any]) -> str:
    """type/items del JSON → notación MD ('string', 'int[]', ...)."""
    if prop["type"] == "array":
        return _JSON_TO_MD_TYPE[prop["items"]["type"]] + "[]"
    return _JSON_TO_MD_TYPE[prop["type"]]

def anthropic_to_md(schema: dict[str, Any]) -> str:
    """dict formato Anthropic → tabla Markdown para humanos."""
    req = set(schema["input_schema"]["required"])
    lines = [
        f"# :{schema['name']}", "", schema["description"], "",
        "| Atributo | Tipo | Obligatorio | Descripción | Ejemplo |",
        "|---|---|---|---|---|",
    ]
    for campo, prop in schema["input_schema"]["properties"].items():
        oblig = "sí" if campo in req else "no"
        ejemplo = f"`{prop['examples'][0]}`" if "examples" in prop else ""
        lines.append(f"| {campo} | {_md_type(prop)} | {oblig} | {prop['description']} | {ejemplo} |")
    return "\n".join(lines) + "\n"
```

> Esto **sustituye** a `_render_schema_md`, `_build_json_prop`, `_MD_TO_JSON_TYPE`, las tablas
> `_NORMA_MD_FIELDS`/`_ANALISIS_MD_FIELDS`/`_NormaField`/`_SchemaField`, y los 8 renderers
> `render_md_*` / `render_json_*`. Todo eso se borra.

---

## 5. Identidad de cada esquema (name + description)

`model_json_schema()` mete el **docstring de la clase** en `description` y `"NormaSchema"` en
`title`. Ninguno sirve: queremos `name="Norma"` (no `"NormaSchema"`) y una descripción pública
(no el docstring de dev). Además `ResultEdge` debe llamarse `RESULT_EDGE`.

**Decisión:** co-locar `name` + `description` públicas **en el propio esquema** vía
`json_schema_extra`, y que `schema_to_anthropic` los lea de ahí (en vez de pasarlos a mano).
Mantiene la regla "el esquema es la única fuente":

```python
class NormaSchema(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "x_name": "Norma",
            "x_description": "Nodo principal del grafo. Una norma consolidada del boletín oficial.",
        },
    )
    ...
```

`schema_to_anthropic` hace `raw.pop("x_name")` / `raw.pop("x_description")` y los usa como
`name`/`description` (firma simplificada: ya no necesita esos params salvo para `EdgeSchema`,
que es paramétrico — ver §7).

---

## 6. Filtrado por flags del nodo `:Norma`

`:Norma` es el único esquema cuyo render **depende de `ParseFlags`** (solo se documentan los
campos que el preprocesador realmente extrae). Hoy ese mapeo flag→campo vive en la primera
columna de `_NORMA_MD_FIELDS`. Para mantener una sola fuente, **el mapeo se mueve al esquema**.

Particularidades a respetar (de los tests/datos actuales):

- Un flag gobierna **varios** campos: `ambito` → `ambito_codigo` + `ambito`; igual `departamento`,
  `rango`, `estado_consolidacion`, `materias`.
- Los flags `metadatos` y `analisis` viven en **submodelos distintos** (`flags.metadatos.*` vs
  `flags.analisis.*`), y cada bloque puede ser `False` entero (cascada: bloque off → todos sus
  campos fuera).
- `notas` (flag de análisis) gobierna el campo `nota`.
- `vigente` es **derivado** (no se parsea): aparece **solo si los 3 flags de estatus**
  (`estatus_derogacion`, `estatus_anulacion`, `vigencia_agotada`) están a `True`.
- `id` **siempre** presente (sin flag).

**Mecanismo:** cada campo declara los flags que requiere (cualificados con su bloque) en
`json_schema_extra`; se incluye si y solo si **todos** están activos:

```python
ambito_codigo: int | None = Field(
    None, description="Código del ámbito territorial", examples=[1],
    json_schema_extra={"x_flags": ["metadatos.ambito"]},
)
vigente: bool | None = Field(
    None, description="Calculado: derogacion=N AND anulacion=N AND vigencia_agotada=N",
    examples=[True],
    json_schema_extra={"x_flags": [
        "metadatos.estatus_derogacion",
        "metadatos.estatus_anulacion",
        "metadatos.vigencia_agotada",
    ]},
)
```

Resolución del filtro (función `_norma_include(flags)` que se pasa como `include=`):

```python
def _flag_on(flags: ParseFlags, ruta: str) -> bool:
    bloque_name, attr = ruta.split(".")          # "metadatos.ambito"
    bloque = getattr(flags, bloque_name)
    return bool(bloque) and getattr(bloque, attr, False) is True  # cascada bloque=False → out
```

`schema_to_anthropic` lee `x_flags` de la property cruda **antes** de limpiarla, aplica el
filtro, y `_clean_prop` descarta `x_flags` (no se incluye en `json_schema_extra` de salida →
ya está cubierto porque `_clean_prop` reconstruye la property con whitelist de claves).

---

## 7. `EdgeSchema` paramétrico (respuesta a "¿descripción variable como parámetros?")

**Sí.** `EdgeSchema` define la **estructura** (campos `relacion_codigo`, `relacion`, `texto`) una
sola vez; las partes variables (`codigo`, `rel_type`) se inyectan como **parámetros** al renderizar
cada relación de `settings.relacion.codigos_a_relacion`.

Enfoque recomendado: **descripciones con plantilla** en el esquema + `.format(...)` al renderizar.

```python
class EdgeSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")
    relacion_codigo: int = Field(
        description="Código de relación BOE ({codigo} = {relacion})", examples=[210])
    relacion: str = Field(
        description="Texto que define la relación ({relacion})", examples=["DEROGA"])
    texto: str = Field(
        description="Descripción libre del alcance de la relación",
        examples=["los arts. 4 a 7 en su totalidad"])

def render_edge(rel_type: str, codigo: int) -> dict[str, Any]:
    """JSON Anthropic de una arista semántica, parametrizada por relación."""
    schema = schema_to_anthropic(
        EdgeSchema,
        name=rel_type,
        description=f"Arista de relación entre normas :Norma. Código BOE: {codigo}.",
    )
    for prop in schema["input_schema"]["properties"].values():
        prop["description"] = prop["description"].format(codigo=codigo, relacion=rel_type)
    schema["example"] = {"relacion_codigo": codigo, "relacion": rel_type,
                         "texto": "los arts. 4 a 7 en su totalidad"}
    return schema
```

Aquí `EdgeSchema` **sí** recibe `name`/`description` por parámetro (no por `x_name`/`x_description`),
porque varían por relación. `schema_to_anthropic` admite ambos modos: si el esquema trae
`x_name`/`x_description` los usa; si no, exige los params.

> **Alternativa (no elegida):** `pydantic.create_model(...)` para fabricar un modelo por relación
> con descripciones ya interpoladas. Más potente pero innecesariamente pesado para 3 relaciones.

---

## 8. Cambios concretos por esquema

| Esquema | `extra="forbid"` | `examples=[...]` por campo | `x_name`/`x_description` | `x_flags` por campo |
|---|---|---|---|---|
| `NormaSchema` | **añadir** | **añadir a todos** | añadir | **añadir** (incl. `vigente`) |
| `EdgeSchema` | **añadir** | añadir (3 campos) | n/a (paramétrico) | n/a |
| `UserQuerySchema` | ya lo tiene | **añadir** (hoy no tiene) | añadir | n/a |
| `ResultEdgeSchema` | ya lo tiene | **añadir** | añadir | n/a |

Los `Field(description=...)` actuales se conservan; solo se les añade `examples` (y `x_flags` en
Norma). Los ejemplos a usar son los que ya viven hoy en las tablas `_NORMA_MD_FIELDS` /
`render_json_*` / los `.md` committeados (se reutilizan, no se inventan).

---

## 9. `generar_esquemas` (queda casi igual, más limpio)

La estructura de carpetas y el `shutil.rmtree` no cambian. Solo cambian las llamadas: ahora
**una** función JSON por esquema y el MD derivado del JSON:

```python
def _write_pair(json_dir, md_dir, nombre, schema):       # helper local
    (json_dir / f"{nombre}.json").write_text(
        json.dumps(schema, ensure_ascii=False, indent=2))
    (md_dir   / f"{nombre}.md").write_text(anthropic_to_md(schema))

# Norma
_write_pair(agents_nodes, humans_nodes, "norma",
            schema_to_anthropic(NormaSchema, include=_norma_include(settings.parse)))
# Aristas semánticas
for codigo, rel_type in settings.relacion.codigos_a_relacion.items():
    _write_pair(agents_edges, humans_edges, rel_type.lower(), render_edge(rel_type, codigo))
# UserQuery / ResultEdge
_write_pair(agents_nodes, humans_nodes, "user_query", schema_to_anthropic(UserQuerySchema))
_write_pair(agents_edges, humans_edges, "result_edge", schema_to_anthropic(ResultEdgeSchema))
```

> `_norma_include` cierra sobre `settings.parse` y devuelve la `Callable[[str], bool]` de §6.
> `name`/`description` de Norma/UserQuery/ResultEdge salen de `x_name`/`x_description`.

---

## 10. Tests — actualizar la deriva existente

`tests/test_preprocess.py` se reescribe en lo tocado (TDD: ajustar/añadir test, luego implementar):

1. **`test_render_md_*` / `test_render_json_*`**: los renderers cambian de firma. Sustituir por
   tests sobre las funciones nuevas (`schema_to_anthropic`, `anthropic_to_md`) y/o sobre el output
   de `generar_esquemas` leyendo los ficheros.
2. **`test_render_md_norma_contiene_id`**: sigue valiendo si se reorienta a leer `norma.md` generado.
3. **`test_render_md_norma_vigente_si_estatus_activos` / `_ausente_si_estatus_incompleto`**:
   mantener la **intención**; ahora `vigente` se controla por `x_flags` (§6). Deben volver a pasar.
4. **`test_render_md_edge_contiene_rel_type`**: reorientar a `render_edge("DEROGA", 210)`.
5. **`test_generar_esquemas_user_query_json_valido`**: **corregir** — ahora `type`,
   `properties`, `additionalProperties:false` viven dentro de `input_schema`, no en la raíz.
   Asertar `schema["input_schema"]["additionalProperties"] is False`.
6. **Nuevos tests del núcleo genérico**:
   - `_collapse_optional` colapsa `anyOf [tipo, null]`.
   - `_clean_prop` quita `title`, quita `default: null`, conserva default real + examples + items.
   - `schema_to_anthropic` produce `name/description/input_schema/example`, con `example` agregado.
   - `anthropic_to_md` mapea `integer→int`, `array<string>→string[]`, marca obligatorios con `sí/no`.
7. **`test_user_query_schema_*` / `test_result_edge_schema_*`**: intactos (validan instancias, no render).

Cobertura ≥ 80% (regla del proyecto). `make check` (ruff + mypy strict + pylint ≥ 8 + complexipy)
debe pasar; vigilar complejidad de `schema_to_anthropic`/`_clean_prop` (extraer helpers si >~5 ramas).

---

## 11. Regenerar artefactos committeados

Tras implementar, ejecutar la generación y **commitear los `.json`/`.md` regenerados** de
`ontology/semantic-layer/{agents,humans}/{nodes,edges}/` para eliminar la deriva actual
(`norma.json` con `vigente`, descripciones que ya no casan, etc.). Verificar a ojo el diff: el
contenido semántico debe ser equivalente al esperado, solo cambiando lo que el refactor corrige.

---

## 12. Fuera de alcance (mencionado, no se toca)

- **Duplicación `Norma` (dataclass de runtime) ↔ `NormaSchema` (BaseModel)**: siguen siendo dos
  modelos paralelos con los mismos campos. Unificarlos es un refactor aparte (afecta a
  `preprocess.py` runtime). **No** se aborda aquí; se deja anotado.
- `Referencia`, `Norma` dataclasses y la carga a Neo4j: intactas.
- `dynamic-layer`: nunca se toca (igual que hoy).
- Consumo de los `.json` por el LLM (`src/llm.py` hoy hardcodea su propio `input_schema` y system
  prompt): fuera de alcance; este plan solo arregla la **generación** de la ontología.

---

## 13. Orden de ejecución (TDD)

1. **RED**: tests del núcleo genérico (`_collapse_optional`, `_clean_prop`, `schema_to_anthropic`,
   `anthropic_to_md`) → fallan.
2. **GREEN**: implementar §4 (núcleo genérico). Verificar tests núcleo.
3. Añadir `extra="forbid"` + `examples` + `x_name`/`x_description` a los 4 esquemas (§5, §8);
   `x_flags` en Norma (§6).
4. Implementar `_norma_include` / `_flag_on` (§6) y `render_edge` (§7). Tests de flags + edge → verde.
5. Reescribir `generar_esquemas` (§9). Borrar tablas y renderers viejos (§4 nota).
6. Corregir/añadir tests de integración de `generar_esquemas` (§10). `make test` ≥ 80%.
7. `make check` limpio.
8. Regenerar y commitear artefactos `ontology/` (§11).
9. Limpiar `src/pruebas.ipynb` si referencia símbolos eliminados (`render_md_norma`, etc.).

### Criterios de éxito (verificables)

- [ ] Cambiar la descripción/ejemplo de un campo se hace **en un solo sitio** (el `Field`).
- [ ] No quedan tablas `_NORMA_MD_FIELDS`/`_ANALISIS_MD_FIELDS` ni renderers `render_*_norma/edge/...`.
- [ ] `agents/*.json` cumplen el formato Anthropic (§3) y `humans/*.md` se generan del JSON.
- [ ] `vigente` aparece/desaparece según los 3 flags de estatus.
- [ ] `make test` (cobertura ≥ 80%) y `make check` pasan.
