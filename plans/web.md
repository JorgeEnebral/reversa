# Plan: Auditoría frontend + arreglo del grafo y filtros (Reversa Web)

## Contexto

La página `/graph` no muestra nada (ni nodos ni aristas) pese a que **sí hay datos** en
Neo4j (22.368 `:Norma`, 5 `:UserQuery`, 38.639 aristas Norma‑Norma `CITA/DEROGA/MODIFICA`
+ `RESULT_EDGE`). El objetivo es: (1) que el grafo se vea, (2) colorear nodos/aristas según
lo pedido, (3) generar **todos los filtros del esquema activo** con el tipo de control
coherente con cada dato, (4) permitir elegir el alcance de nodos (solo `UserQuery`, solo
legislación `Norma`, o todos), y (5) dejar el código modularizado a nivel senior.

## Auditoría — errores encontrados (perfil frontend senior)

| # | Severidad | Fichero | Problema |
|---|---|---|---|
| 1 | **Crítico** | `components/sigma_canvas.py` | **Causa raíz del “no sale nada”.** El `ui.html('<div id="sigma-canvas" …height:100%>')` queda envuelto en un div NiceGUI de altura `auto`; `#sigma-canvas` resuelve `height:100%` contra un padre de altura 0 → canvas de Sigma de **0px** → no se ve nada. |
| 2 | **Alto** | `pages/graph.py` `_query_graph` | **Las aristas nunca aparecen.** `LIMIT 100` muestrea 100 nodos al azar de 22k y luego descarta toda arista cuyos dos extremos no estén en esos 100 → ~0 aristas. |
| 3 | **Alto** | `pages/graph.py` / `components/filter_panel.py` | **`:UserQuery` y `RESULT_EDGE` no se consultan nunca.** Imposible ver consultas; no hay selector de alcance. |
| 4 | **Medio** | `components/filter_panel.py` | **Filtro `departamento` muerto:** está `False` en `ParseFlags`, no existe en los nodos → siempre devuelve vacío (incoherente). Los filtros están **hardcodeados**, no derivados del esquema. |
| 5 | **Medio** | `pages/graph.py` | Cypher frágil: `where_str.replace('n.', 'a.')` para reusar el WHERE en la query de aristas. Se rompe si un valor/param contiene `n.`. |
| 6 | **Medio** | `pages/graph.py` | Se crea y cierra un `GraphDatabase.driver` **en cada “Aplicar”**. El driver debe ser singleton de módulo (su creación es cara). |
| 7 | **Medio** | `static/sigma_bridge.js` | Colores hardcodeados (`#2f6fb0`, `#e74c3c`, `#cbd5e1`) desacoplados de los design tokens. `vigente===false`→rojo pisa el esquema de color pedido. |
| 8 | **Bajo** | `components/sigma_canvas.py` | Detección de clicks por **polling cada 500 ms** (`ui.timer` + `window.getLastClick`): laggy y poco idiomático. Mejor `emitEvent` → `ui.on`. |
| 9 | **Bajo** | `pages/graph.py` | Dependencia CDN en runtime sin fallback (unpkg). |
| 10 | **Bajo** | `static/sigma_bridge.js` | Sin layout: posiciones aleatorias → “hairball” disperso e ilegible. |
| 11 | **Bajo** | `components/info_panel.py` | Vuelca todos los atributos crudos (incl. `*_codigo`); sin formato. |

## Decisiones tomadas (usuario)

- **Filtros enum** (`rango`, `estado_consolidacion`, `estatus_*`, `vigencia_agotada`): **desplegable con valores reales** del grafo (query `DISTINCT` cacheada).
- **Layout**: **ForceAtlas2** (vía bundle `graphology-library`, global `graphologyLibrary.layoutForceAtlas2`).
- **Librerías JS**: **vendorizadas** en `src/web/static/vendor/` (no CDN).

## Colores (design tokens, fuente única en Python — `theme.py`)

- Nodos `:Norma` → **verde claro** `#86efac` (borde `#22c55e`).
- Nodos `:UserQuery` → **azul** `#2f6fb0`.
- Aristas → **negro** `#111111`.

Se asignan en el servicio Python (por `kind` de nodo y por arista) y se envían en el payload;
el JS deja de hardcodear colores.

## Modularización objetivo

```
src/web/
  theme.py                 ← NUEVO: design tokens (colores grafo)
  data/
    __init__.py
    graph_repo.py          ← NUEVO: acceso Neo4j (driver singleton, fetch_graph, distinct_values, build_where)
  components/
    filter_panel.py        ← REESCRITO: filtros schema-driven por tipo + selector de alcance
    sigma_canvas.py        ← arregla altura, colores por payload, clicks por evento
    info_panel.py          ← (menor) formato de atributos
  pages/
    graph.py               ← solo orquestación UI (sin Cypher); usa graph_repo
  static/
    sigma_bridge.js        ← ForceAtlas2 + color por kind, sin colores hardcodeados
    vendor/                ← NUEVO: graphology.umd.min.js, sigma.min.js, graphology-library.min.js
```

Principio: **presentación** (`pages/`, `components/`) separada de **datos** (`data/graph_repo.py`)
y de **estilo** (`theme.py`). El esquema (`src/semantic_schemas.py`) sigue siendo la única
fuente de verdad de los campos.

## Implementación por requisito

### 1. Arreglar el render (no sale nada) — `components/sigma_canvas.py`
- `#sigma-canvas` con `position:absolute; inset:0;` dentro del contenedor `position:relative`,
  independiente de la cadena de `height:100%`. Sin doble envoltura `ui.element` + `ui.html`.

### 2. Aristas visibles + alcance — `data/graph_repo.py`
- **Driver singleton** de módulo.
- `fetch_graph(scope, filters)`: edges‑first para `norma`; `RESULT_EDGE` para `userquery`;
  unión para `all`. Cada nodo lleva `kind` + `color`; aristas en negro.
- `build_where(alias, filters)`: WHERE con alias correcto y params namespaced (sin `replace`).
- `distinct_values(field)` cacheado (`lru_cache`), campo validado contra allowlist del esquema.

### 3. Filtros schema-driven + tipos coherentes — `components/filter_panel.py`
- Campos activos vía `schema_to_anthropic(NormaSchema, include=_norma_include(settings.parse))`.
- Mapeo tipo→widget: `boolean`→tri-select; `fecha_*`→rango año; `S/N`→select; enum→select de
  valores reales; string libre→input CONTAINS; `int`→number. Pares `*_codigo` colapsados.

### 4. Selector de alcance — `components/filter_panel.py`
- `ui.toggle({"all","norma","userquery"})`; al elegir `userquery` se ocultan filtros de Norma.

### 5. ForceAtlas2 + vendoring — `static/`
- Cargar `vendor/*.js` locales; correr `graphologyLibrary.layoutForceAtlas2.assign(graph, …)`
  antes de instanciar Sigma. Color por `kind` desde payload.

### 6. Clicks por evento — `sigma_canvas.py` + `sigma_bridge.js`
- `emitEvent('graph_click', …)` en JS → `ui.on('graph_click', …)` en Python. Sin `ui.timer`.

### 7. Limpieza derivada
- `info_panel.py`: ocultar `*_codigo` y attrs internos; `graph.py` solo orquesta.

## Verificación

1. `make check` y `make test` (cobertura ≥ 80%).
2. Tests: unit (`build_where`, mapeo tipo→widget, `fetch_graph` mockeado), integración
   (`distinct_values`/`fetch_graph` contra Neo4j), e2e Playwright (`/graph` pinta >0 nodos/aristas;
   alcance “Consultas” muestra `UserQuery`+`RESULT_EDGE`).
3. Manual: `uv run python -m src.main` → `/graph`: Norma verde claro, UserQuery azul, aristas
   negras; filtros del esquema activo con control coherente; layout ForceAtlas2.
