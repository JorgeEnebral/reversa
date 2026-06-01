# Plan — Referencias posteriores en la generación del grafo

## Objetivo

Hoy el grafo solo materializa aristas desde `<anteriores>`. Una arista `A→B` queda
fuera del grafo cuando **A no está en `raw/`** (su fichero no existe, así que su
`<anteriores>` nunca se procesa). Esa misma arista sí aparece en el `<posteriores>`
de B. Hay que añadir el procesado de `<posteriores>` para no perder esas aristas,
**sin duplicar** las que ya genera `<anteriores>` y **sin faltar** ninguna.

## Invariantes confirmadas en el corpus (evidencia, no supuestos)

1. **Dirección.** En `<anteriores>` de X, `id_norma` es el nodo **destino**: arista
   `X → id_norma` (X es el actor: "X MODIFICA id_norma"). En `<posteriores>` de X,
   `id_norma` es el nodo **origen**: arista `id_norma → X` (la norma posterior actúa
   sobre X: texto en pasiva "SE MODIFICA … por …").
2. **Mismo código, texto en pasiva.** `<posteriores>` usa el mismo `relacion codigo`
   que el `<anteriores>` correlativo (270, 210), solo cambia el texto a pasiva
   ("SE MODIFICA", "SE DEROGA"). ⇒ Se mapea por **código** vía
   `codigos_a_relacion`, igual que anteriores. El `relacion` literal no se usa.
3. **CITA (330) NUNCA aparece en `<posteriores>`** (verificado sobre 5.000 ficheros).
   Se cumple la invariante: las CITA solo existen en `<anteriores>`. ⇒ El procesado
   de posteriores no necesita lógica especial para CITA.
4. **`stem` del fichero == `<identificador>`** (p.ej. `BOE-A-2013-11502.xml`).
   ⇒ El conjunto de ids consolidados en `raw/` se obtiene de los nombres de fichero,
   sin parsear.
5. Solo los códigos en `codigos_a_relacion` (210→DEROGA, 270→MODIFICA, 330→CITA)
   generan aristas; el resto se ignora (igual que hoy en anteriores).

## Algoritmo (matriz A→B, con `raw_ids` = ids de ficheros en `raw/`)

Para cada arista `A→B` (no-CITA salvo donde se indique), se materializa **exactamente
una vez** y con el texto correcto:

| Caso | A en raw | B en raw | Quién la crea | Nodo stub | Texto |
|---|---|---|---|---|---|
| 1 | sí | sí | `<anteriores>` de A | — | anterior (de A) |
| 2 | sí | no | `<anteriores>` de A | B (solo `id`) | anterior (de A) |
| 3 | no | sí | `<posteriores>` de B | A (solo `id`) | posterior (de B) |
| 4 | no | no | nadie (no observable) | — | — |

**Regla de deduplicación (clave):** al procesar `<posteriores>` de una norma X
(origen = `ref.id_norma` = Z, destino = X):

- **Si Z ∈ `raw_ids` → SKIP.** La arista `Z→X` ya la crea (o creará) el
  `<anteriores>` de Z. Esto evita el doble conteo del caso 1.
- **Si Z ∉ `raw_ids` → crear** stub `Z {id}` + arista `Z→X` con el texto del
  posterior (caso 3).

La regla de texto del enunciado ("siempre el texto de anterior, salvo que A no esté
en raw/ → texto de B") queda satisfecha **automáticamente**: anteriores siempre usa
texto-de-anterior; posteriores solo dispara cuando el origen no está en raw/, y ahí
usa texto-de-posterior. Los dos caminos son disjuntos, así que no compiten.

CITA: como nunca está en posteriores (invariante 3), las CITA siguen creándose solo
desde anteriores (casos 1 y 2). Sin cambios para ellas.

## Cambios por fichero

### 1. `src/config.py` — `AnalisisFlags`
- Añadir `referencias_posteriores: bool = True`.
- Actualizar el docstring de la clase: hoy dice que posteriores se omite "por
  redundante"; pasar a explicar que se procesa **solo** para recuperar aristas cuyo
  **origen no está en `raw/`** (deduplicado contra anteriores).

### 2. `src/semantic_schemas.py` — dataclass `Norma`
- Añadir `referencias_posteriores: list[Referencia] = field(default_factory=list)`
  (reutiliza el dataclass `Referencia`, misma forma).
- Ajustar el comentario del docstring de `Norma` para mencionar también posteriores
  como aristas.
- **`NormaSchema`: SIN CAMBIOS** (decisión confirmada). Las referencias son aristas,
  no propiedades de nodo, así que no se documentan en `norma.json`/`norma.md`.

### 3. `src/preprocess.py` — `_parse_analisis`
- Tras el bloque `referencias_anteriores`, añadir bloque análogo gated por
  `f.referencias_posteriores`:
  ```python
  if f.referencias_posteriores:
      posteriores = analisis_el.find("referencias/posteriores")
      if posteriores is not None:
          for post in posteriores.findall("posterior"):
              rel_el = post.find("relacion")
              norma.referencias_posteriores.append(
                  Referencia(
                      id_norma=post.findtext("id_norma", ""),
                      relacion_codigo=_int_attr(rel_el, "codigo") or 0,
                      relacion=rel_el.text or "" if rel_el is not None else "",
                      texto=post.findtext("texto", ""),
                  )
              )
  ```

### 4. `src/preprocess.py` — `_upsert_norma`
- Excluir `referencias_posteriores` de las props del nodo (igual que
  `referencias_anteriores`), si no `asdict` intentaría escribir una lista de dicts
  como propiedad:
  ```python
  if k not in ("id", "referencias_anteriores", "referencias_posteriores") and v is not None
  ```

### 5. `src/preprocess.py` — `_upsert_relacion`
- Cambiar `MATCH (a:Norma {id: $src})` → **`MERGE (a:Norma {id: $src})`**. Necesario
  para que las aristas de posteriores creen el **stub del origen** (Z ∉ raw/). Es
  inocuo para anteriores: el origen es la norma actual, ya upserted, y `MERGE` la
  encuentra. Direccion sigue siendo `src → dst`, decidida por el caller.
- Corregir el docstring (hoy dice "MATCH en ambos nodos … no se crean stubs", lo cual
  ya es falso porque usa `MERGE (b)`): describir que ambos extremos se `MERGE`-an
  (stub `{id}` para el que no esté consolidado) y la arista se `CREATE`-a.

### 6. `src/preprocess.py` — conjunto `raw_ids`
- Añadir método cacheado que devuelve los ids consolidados a partir de los nombres de
  fichero (lazy, porque los tests reasignan `api_raw_dir` tras construir):
  ```python
  def _ids_consolidados(self) -> set[str]:
      if self._raw_ids is None:
          self._raw_ids = {
              f.stem for d in self.api_raw_dir.iterdir() if d.is_dir()
              for f in d.glob("*.xml")
          }
      return self._raw_ids
  ```
  con `self._raw_ids: set[str] | None = None` en `__init__`.

### 7. `src/preprocess.py` — helper compartido + `_procesar_fichero`
Para no duplicar la lógica de dedup entre `_procesar_fichero` y `reintentar` (que ya
es casi idéntico), extraer un helper que emita **ambas** familias de aristas:

```python
def _materializar_aristas(self, session, norma, raw_ids) -> int:
    """Crea aristas de anteriores y posteriores. Devuelve nº creadas."""
    n = 0
    codigos = self._cfg.relacion.codigos_a_relacion
    # anteriores: norma -> ref (texto del anterior). stub para ref ∉ raw/
    for ref in norma.referencias_anteriores:
        rel = codigos.get(ref.relacion_codigo)
        if rel:
            self._upsert_relacion(session, norma.id, rel, ref.id_norma,
                                  ref.relacion_codigo, ref.texto)
            n += 1
    # posteriores: ref -> norma, SOLO si el origen ref ∉ raw/ (dedup vs anteriores)
    for ref in norma.referencias_posteriores:
        if ref.id_norma in raw_ids:
            continue
        rel = codigos.get(ref.relacion_codigo)
        if rel:
            self._upsert_relacion(session, ref.id_norma, rel, norma.id,
                                  ref.relacion_codigo, ref.texto)
            n += 1
    return n
```

- `_procesar_fichero`: sustituir el bucle actual de anteriores por
  `resumen.aristas_upsert += self._materializar_aristas(session, norma, self._ids_consolidados())`.

### 8. `src/preprocess.py` — `reintentar`
- Reemplazar su bucle de anteriores por la misma llamada a `_materializar_aristas`
  (con `self._ids_consolidados()`), para que los reintentos apliquen idéntica lógica
  de posteriores/dedup.

## Tests (TDD: rojo → verde)

`tests/test_preprocess.py` (fixture `FIXTURE_39` ya tiene un `<posterior>` a
`BOE-A-2020-3824` con código 270):

1. **Reemplazar** `test_parser_ignora_referencias_posteriores` por
   `test_parser_extrae_referencias_posteriores`:
   - `referencias_anteriores` **no** contiene `BOE-A-2020-3824` (sigue separado).
   - `referencias_posteriores` **sí** lo contiene, con `relacion_codigo == 270`.
2. `test_parser_posteriores_vacio_si_flag_false`: con
   `AnalisisFlags(referencias_posteriores=False)`, `norma.referencias_posteriores == []`.
3. **Dedup — origen en raw/**: tmp dir con `BOE-A-2015-10565.xml` **y**
   `BOE-A-2020-3824.xml`. Como el origen del posterior está en raw/, no debe emitirse
   arista extra desde el posterior (la cuenta de aristas DEROGA/MODIFICA coincide con
   las de anteriores; sin `CREATE` duplicado entre los dos nodos).
4. **Origen NO en raw/**: tmp dir solo con `BOE-A-2015-10565.xml`. El posterior a
   `BOE-A-2020-3824` (no en raw/) debe producir: un `MERGE` de stub para
   `BOE-A-2020-3824` y un `CREATE` de arista `BOE-A-2020-3824 → BOE-A-2015-10565`
   (dirección invertida respecto a anteriores), con el texto del posterior.
5. Verificar que `_upsert_norma` no escribe `referencias_posteriores` como propiedad
   (revisar el dict `props` del `MERGE … SET n += $props`).

Mantener cobertura ≥ 80 % (`make test`).

## Verificación final
- `make check` (ruff + mypy + pylint ≥ 8 + complexipy) — vigilar complejidad de
  `_materializar_aristas` (por eso se extrae como helper).
- `make test` verde con la cobertura mínima.
- Comprobación manual sobre un caso real conocido (norma con `<posteriores>` cuyo
  origen no esté en `raw/`) tras un `preprocesar_todo`: la arista invertida existe y
  el grafo no tiene aristas duplicadas entre pares consolidados.

## Puntos abiertos / decisiones tomadas
- **NormaSchema sin cambios** (confirmado): las referencias son aristas, no props.
- **`CREATE` vs `MERGE` en la arista**: se mantiene `CREATE`. La dedup
  anteriores↔posteriores se resuelve a nivel de aplicación (regla de skip), que es el
  único duplicado que introduce este cambio. Duplicados *dentro del mismo fichero*
  (una norma que lista el mismo `id_norma`+código dos veces) son preexistentes y
  quedan fuera de alcance; si se quisiera idempotencia dura habría que cambiar a
  `MERGE (a)-[r:REL {codigo}]->(b) SET r.texto=…`, lo que alteraría la semántica
  actual de anteriores.
