# Estructura del Derecho español y de la API del BOE

Este documento describe **dos cosas**:

1. **Cómo se organiza el ordenamiento jurídico español**: jerarquía de normas, partes internas de un texto legal (libros, títulos, capítulos, artículos, apartados…), y conceptos transversales (vigencia, derogación, anulación, consolidación).
2. **Cómo lo expone la API de datos abiertos del BOE**: bloques, campos exactos con tipo y obligatoriedad, vocabularios controlados, verbos de relación y un ejemplo real completo.

> Datos verificados con `curl` real contra `https://www.boe.es/datosabiertos/api/` el 2026-05-27, complementado con el PDF oficial `resources/datos_boe.pdf` (*"API para el acceso a la colección de Legislación Consolidada"*, AEBOE, 2 sept. 2025).

---

## Parte 1 — Estructura jurídica española

### 1.1 Jerarquía normativa (orden descendente)

La Constitución es la norma suprema (CE, art. 9.1); por debajo, el principio de **jerarquía normativa** (CE, art. 9.3) determina el orden. La API codifica cada nivel en el campo `rango.codigo`.

| Código (`rango.codigo`) | Texto oficial | Quién la dicta | Ejemplo |
|---|---|---|---|
| `1070` | **Constitución** | Cortes + refrendo popular | Constitución Española de 1978 |
| `1180` | **Acuerdo Internacional** | Tratados ratificados | Convenio de Roma |
| `1290` | **Ley Orgánica** | Cortes Generales (mayoría absoluta) | LO 6/1985 del Poder Judicial |
| `1300` | **Ley** | Cortes Generales (mayoría simple) | Ley 39/2015 |
| `1450` | **Ley Foral** | Parlamento de Navarra | Ley Foral 14/2007 |
| `1310` | **Real Decreto Legislativo** | Gobierno con delegación de las Cortes (texto refundido) | RDL 1/1995 ET |
| `1320` | **Real Decreto-ley** | Gobierno por urgencia (CE art. 86) | RDL 8/2020 COVID |
| `1500` | **Decreto-ley** | Gobierno autonómico equivalente | DL 8/2020 Cataluña |
| `1470` | **Decreto Legislativo** | Gobierno autonómico texto refundido | — |
| `1480` | **Decreto Foral Legislativo** | Gobierno foral navarro | — |
| `1325` | **Decreto-ley Foral** | Gobierno foral navarro | — |
| `1340` | **Real Decreto** | Presidente del Gobierno / Consejo de Ministros | RD 463/2020 estado de alarma |
| `1510` | **Decreto** | Gobierno autonómico | — |
| `1220` | **Reglamento** | Variado | RD 1720/2007 LOPD |
| `1020` | **Acuerdo** | Consejo de Ministros / órganos colegiados | — |
| `1350` | **Orden** | Ministros / Consejeros | OM ICT/728/2024 |
| `1370` | **Resolución** | Direcciones generales y similares | — |
| `1410` | **Instrucción** | Órganos administrativos a inferiores | — |
| `1390` | **Circular** | Banco de España, CNMV, etc. | Circular BdE 2/2016 |

Los **rangos** completos los devuelve `GET /datosabiertos/api/datos-auxiliares/rangos` (Accept: application/json) — son 19 entradas tal cual.

### 1.2 Estructura interna de un texto legal

Una norma extensa se divide jerárquicamente. No todas las normas usan todos los niveles; el orden de mayor a menor es:

```
Norma
  └── Libro          (solo en grandes códigos: Civil, Penal, LEC, LOPJ, etc.)
       └── Título
            └── Capítulo
                 └── Sección
                      └── Subsección
                           └── Artículo                       ← unidad jurídica básica
                                ├── Apartado                  (numerado: 1, 2, 3…)
                                │    └── Letra/párrafo        (a, b, c… o letra-cursiva)
                                └── Letra
  └── Disposiciones (al final del texto)
       ├── Disposición adicional
       ├── Disposición transitoria
       ├── Disposición derogatoria
       └── Disposición final
  └── Anexos
```

**Convenciones de cita estándar** (las que el corpus respeta y nuestro RAG debe entender):
- `art. 21` — Artículo entero.
- `art. 21.3` — Apartado 3 del artículo 21.
- `art. 21.3.b)` — Letra b) del apartado 3 del artículo 21.
- `D.A. 8ª` — Disposición adicional octava.
- `D.T. 3ª` — Disposición transitoria tercera.
- `D.D. única` — Disposición derogatoria única.
- `D.F. 7ª` — Disposición final séptima.
- `prólogo` / `preámbulo` / `exposición de motivos` — sin numerar.

En la API, cada uno de estos niveles aparece como un `<bloque>` con `tipo` en {`nota_inicial`, `preambulo`, `instrumento`, `parte_dispositiva`, `parte_final`, `encabezado`, `precepto`, `firma`}. Los **artículos vivos** son `tipo="precepto"`.

### 1.3 Vida y muerte de una norma (vigencia, derogación, anulación)

Cuatro conceptos distintos que la API distingue con campos separados:

| Concepto | Significado | Campo en la API |
|---|---|---|
| **Entrada en vigor** | Cuándo empieza a producir efectos | `fecha_vigencia` (DATE, opcional) |
| **Vigencia agotada** | La norma cumplió su propósito temporal (ej. ley anual de presupuestos) | `vigencia_agotada` (`S`/`N`) |
| **Derogación** | Una norma posterior la deja sin efecto (total o parcial) | `estatus_derogacion` (`S`/`N`) + `fecha_derogacion` |
| **Anulación** | El TC u órgano competente la declara nula desde origen | `estatus_anulacion` (`S`/`N`) + `fecha_anulacion` |

**Importante** (verificado): `estatus_derogacion` **NO es un enum** con valores tipo "vigente / derogada total / derogada parcial". Es **booleano `S`/`N`**. El matiz "derogada parcialmente" hay que extraerlo del bloque `referencias.posteriores` buscando relaciones con `codigo` ∈ {`211`, `212`, `213`, `214`, `215`, `216`, `217`} (ver tabla §2.6).

**Estado de consolidación** (`estado_consolidacion`) son solo **2 valores**:

| Código | Texto | Significado |
|---|---|---|
| `3` | **Finalizado** | La consolidación está al día con todas las modificaciones publicadas |
| `4` | **Desactualizado** | Hay modificaciones publicadas no integradas todavía en el texto consolidado |

### 1.4 Tipos de relaciones entre normas (los "verbos")

Cuando una norma habla de otra, lo hace con uno de los **53 verbos** documentados en `relaciones-anteriores` / `relaciones-posteriores`. Los **importantes para los 4 briefings del GOAL** son:

| Familia | Códigos | Importancia para GOAL |
|---|---|---|
| **MODIFICA** (briefings 1 y 2) | `270`, `271`, `272` | 🔴 Crítica — cuenta "veces que A modifica a B" para encontrar omnibus y normas más enmendadas |
| **DEROGA / derogación parcial** | `210`–`217` | 🔴 Crítica — distinguir derogación total (`210`) de parcial (`211`–`217`) |
| **ANULA** | `220`, `221` | 🟡 Importante — anulaciones tienen efecto retroactivo |
| **CITA / EN RELACIÓN** (briefings 3 y 4) | `330`, `331` | 🔴 Crítica — encontrar normas vivas que citan normas muertas |
| **AÑADE / SUSTITUYE / SUPRIME** | `407`, `245`, `235` | 🟡 Importante — equiparable a modificación |
| **DESARROLLA** | `490` | 🟢 Contexto — útil para chains (Ley → Reglamento) |
| **TRANSPONE** | `426`, `427` | 🟢 Contexto — derecho UE |
| **APRUEBA** | `420` | 🟢 Contexto — Real Decreto que aprueba un reglamento, etc. |
| **DEJA SIN EFECTO / SUSPENDE** | `230`, `231` | 🟡 Importante — efecto análogo a derogación temporal |
| **CORRECCIONES** | `201`–`204` | 🟢 No estructural — corregir erratas, no cambian fondo |

El catálogo completo está en la sección §2.6.

---

## Parte 2 — La API del BOE en detalle

### 2.1 Endpoints (legislación consolidada)

Base: `https://www.boe.es/datosabiertos/api/legislacion-consolidada`. Método siempre `GET`. Selección de formato por cabecera HTTP `Accept` (`application/json` o `application/xml`). Sin API key.

| Ruta | Devuelve | JSON | XML |
|---|---|---|---|
| `/legislacion-consolidada` | Lista paginada con `from`/`to`/`offset`/`limit`/`query` | ✅ | ✅ |
| `/legislacion-consolidada/id/{id}` | Norma completa (metadatos + analisis + metadata-eli + texto) | ❌ | ✅ |
| `/legislacion-consolidada/id/{id}/metadatos` | Solo metadatos | ✅ | ✅ |
| `/legislacion-consolidada/id/{id}/analisis` | Solo análisis (materias, notas, referencias) | ✅ | ✅ |
| `/legislacion-consolidada/id/{id}/metadata-eli` | Metadatos ELI | ❌ | ✅ |
| `/legislacion-consolidada/id/{id}/texto` | Texto consolidado completo (todas las versiones) | ❌ | ✅ |
| `/legislacion-consolidada/id/{id}/texto/indice` | Índice jerárquico de bloques | ✅ | ✅ |
| `/legislacion-consolidada/id/{id}/texto/bloque/{id_bloque}` | Un bloque concreto (todas sus versiones) | ❌ | ✅ |

**Tablas auxiliares** (vocabularios controlados, descarga única):
| Ruta | Contenido | Tamaño |
|---|---|---|
| `/datos-auxiliares/rangos` | 19 niveles normativos | ~500 B |
| `/datos-auxiliares/estados-consolidacion` | 2 estados | ~84 B |
| `/datos-auxiliares/ambitos` | Estatal/autonómico | pequeño |
| `/datos-auxiliares/departamentos` | ~70 organismos emisores | ~10 KB |
| `/datos-auxiliares/materias` | ~1300 materias jurídicas | ~337 KB |
| `/datos-auxiliares/relaciones-anteriores` | 53 verbos en voz activa | ~1.4 KB |
| `/datos-auxiliares/relaciones-posteriores` | 53 verbos en voz pasiva | ~1.4 KB |

### 2.2 Bloque `metadatos`

| Campo | Tipo | Formato | Obligatorio | Descripción |
|---|---|---|---|---|
| `identificador` | `CHAR(20)` | `[A-Z]{3}-[A-Z]-\d{4}-\d{1,5}` | ✅ | Clave primaria de la norma. Ej.: `BOE-A-2015-10565` |
| `fecha_actualizacion` | `TIME` | `AAAAMMDDTHHmmSSZ` (UTC) | ✅ | Última vez que la AEBOE tocó esta consolidada — clave para ingesta incremental |
| `ambito.codigo` / `ambito.texto` | `NUMBER` / `CHAR(20)` | `1`=Estatal, `2`=Auton… | ✅ | Ámbito territorial |
| `departamento.codigo` / `departamento.texto` | `NUMBER` / `CHAR(100)` | p.ej. `7723`=Jefatura del Estado, `4810`=Ministerio de Justicia | ✅ | Órgano emisor |
| `rango.codigo` / `rango.texto` | `NUMBER` / `CHAR(100)` | Ver tabla §1.1 | ✅ | Nivel normativo |
| `titulo` | `CHAR(4000)` | — | ✅ | Título oficial, en mayúsculas y/o cursiva legal |
| `numero_oficial` | `CHAR(20)` | `39/2015`, `JUS/987/2020`, `PCM/997/2022` | ⚪ | Numeración oficial publicada |
| `diario` | `CHAR(200)` | "Boletín Oficial del Estado" | ✅ | Diario oficial — casi siempre constante para ámbito estatal |
| `diario_numero` | `NUMBER` | — | ✅ | Número del diario donde se publicó |
| `fecha_disposicion` | `DATE` | `AAAAMMDD` | ⚪ | Fecha de aprobación |
| `fecha_publicacion` | `DATE` | `AAAAMMDD` | ✅ | Fecha de publicación en el BOE |
| `fecha_vigencia` | `DATE` | `AAAAMMDD` (puede ser vacío) | ⚪ | Entrada en vigor |
| `estatus_derogacion` | `CHAR(1)` | `S` / `N` | ✅ | ¿Derogada? (boolean) |
| `fecha_derogacion` | `DATE` | `AAAAMMDD` (vacío si N) | ⚪ | Fecha en que se derogó |
| `estatus_anulacion` | `CHAR(1)` | `S` / `N` | ✅ | ¿Anulada? (boolean) |
| `fecha_anulacion` | `DATE` | — | ⚪ | Fecha de anulación |
| `vigencia_agotada` | `CHAR(1)` | `S` / `N` | ✅ | ¿Vigencia agotada por cumplimiento del fin? |
| `estado_consolidacion.codigo` / `.texto` | `NUMBER` / `CHAR(100)` | `3`=Finalizado, `4`=Desactualizado | ✅ | Estado de la consolidación |
| `url_eli` | `CHAR(150)` | `https://www.boe.es/eli/es/{tipo}/{AAAA}/{MM}/{DD}/{numero}` | ⚪ | Permalink ELI (European Legislation Identifier) |
| `url_html_consolidada` | `CHAR(150)` | `https://www.boe.es/buscar/act.php?id={id}` | ✅ | URL HTML legible — reconstruible desde `identificador`, redundante |

**Tipos lógicos (deducidos):**
- `CHAR(N)` = string UTF-8 de longitud máxima N.
- `NUMBER` = entero positivo.
- `DATE` = string `\d{0,8}` (puede estar vacío).
- `TIME` = string `\d{14}Z` siempre presente.

### 2.3 Bloque `analisis`

Estructura general:

```
analisis
  ├── materias[]
  ├── notas[]
  └── referencias
       ├── anteriores[]   ← lo que esta norma hace a normas previas
       └── posteriores[]  ← lo que normas posteriores le han hecho a esta
```

#### 2.3.1 `materias[]`

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `materia.codigo` | `NUMBER` | ✅ | Código de materia (vocabulario controlado de ~1300 entradas) |
| `materia.texto` | `CHAR(200)` | ✅ | Descripción legible. Ej.: `Adopción`, `Seguridad Social` |

#### 2.3.2 `notas[]`

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `nota` | `array<CHAR(1500)>` | ✅ | Notas en texto libre. Ej.: `"Entrada en vigor, con la salvedad indicada, el 2 de octubre de 2016"` |

#### 2.3.3 `referencias.anteriores[]` y `referencias.posteriores[]`

Mismo esquema, solo cambia la voz del verbo (activa vs pasiva).

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `id_norma` | `CHAR(20)` | ✅ | Identificador BOE-A de la otra norma |
| `relacion.codigo` | `NUMBER` | ✅ | Código del verbo (tabla §2.6) |
| `relacion.texto` | `CHAR(256)` | ✅ | Verbo en lenguaje natural. ⚠ El **texto cambia** entre anteriores (`DEROGA`) y posteriores (`SE DEROGA`); el `codigo` **no cambia** |
| `texto` | `CHAR(1500)` | ⚪ | Texto libre que precisa el alcance. Ej.: `"los arts. 4 a 7 de la Ley 2/2011, de 4 de marzo"` |

**Regla de oro**: para construir el grafo, **siempre comparar por `relacion.codigo`** y nunca por `relacion.texto`.

### 2.4 Bloque `metadata-eli`

Solo XML. Contiene metadatos siguiendo la ontología **ELI** (European Legislation Identifier, W3C). Útil si se quiere interoperar con otras bases de datos legislativas europeas, pero para el alcance de Reversa el `url_eli` que ya viene en `metadatos` es suficiente.

Referencias oficiales:
- <https://boe.es/legislacion/eli.php>
- <https://elidata.es>

### 2.5 Bloque `texto`

Solo XML. Cada texto consolidado se compone de **bloques** y cada bloque tiene **una o varias versiones** (porque el texto va cambiando con cada modificación):

```xml
<texto>
  <bloque id="art21" tipo="precepto" titulo="Artículo 21. Obligación de resolver"
          [fecha_caducidad="..."]>
    <version fecha_publicacion="20151002" fecha_vigencia="20161002"
             id_norma="BOE-A-2015-10565">
      <p class="..."> ... </p>
    </version>
    <version fecha_publicacion="20220713"
             id_norma="BOE-A-2022-11589">
      <p class="..."> ... </p>
    </version>
  </bloque>
  ...
</texto>
```

Atributos de `<bloque>`:

| Atributo | Valores |
|---|---|
| `id` | identificador del bloque, usado en `/texto/bloque/{id_bloque}` |
| `tipo` | `nota_inicial`, `preambulo`, `instrumento`, `encabezado`, `parte_dispositiva`, `precepto`, `parte_final`, `firma` |
| `titulo` | Ej.: `Artículo 21. Obligación de resolver` |
| `fecha_caducidad` | Opcional. Si está, el bloque deja de mostrarse a partir de esa fecha |

Atributos de `<version>`:

| Atributo | Valores |
|---|---|
| `fecha_publicacion` | DATE de cuándo se publicó esta versión |
| `fecha_vigencia` | DATE opcional |
| `id_norma` | BOE-A de la norma modificadora que introdujo esta versión |

Contenidos posibles dentro de `<version>`: `<p>` con `class` CSS, `<table>` HTML estándar, `<img>` (**PNG codificadas en base64 inline** — pueden inflar mucho el payload), `<blockquote>` con HTML anidado.

### 2.6 Catálogo completo de verbos de relación

Salida verbatim de `GET /datos-auxiliares/relaciones-anteriores` y `…/relaciones-posteriores` el 2026-05-27.

| `codigo` | Texto (anterior — voz activa) | Texto (posterior — voz pasiva) | Familia |
|---|---|---|---|
| `201` | CORRECCIÓN de errores | CORRECCIÓN de errores | corrección |
| `202` | CORRECCIÓN de erratas | CORRECCIÓN de erratas | corrección |
| `203` | CORRIGE errores | SE CORRIGEN errores | corrección |
| `204` | CORRIGE erratas | SE CORRIGEN erratas | corrección |
| `210` | **DEROGA** | **SE DEROGA** | derogación |
| `211` | DEROGA lo indicado | SE DEROGA lo indicado | derogación parcial |
| `212` | DEROGA con la excepción indicada | SE DEROGA con la excepción indicada | derogación parcial |
| `213` | DEROGA en cuanto se oponga | SE DEROGA en cuanto se oponga | derogación parcial |
| `214` | DEROGA en la forma indicada | SE DEROGA en la forma indicada | derogación parcial |
| `215` | **DEROGA parcialmente** | SE DEROGA parcialmente | derogación parcial |
| `216` | DEROGA de forma reiterada | Se DEROGA de forma reiterada | derogación parcial |
| `217` | DEROGA tácitamente | SE DEROGA tácitamente | derogación |
| `220` | ANULA | SE ANULA | anulación |
| `221` | ANULA las ediciones anteriores de las normas | SE ANULAN las ediciones anteriores de las normas | anulación |
| `230` | DEJA SIN EFECTO | SE DEJA SIN EFECTO | suspensión |
| `231` | SUSPENDE | SE SUSPENDE | suspensión |
| `235` | SUPRIME | SE SUPRIME | modificación |
| `245` | SUSTITUYE | SE SUSTITUYE | modificación |
| `247` | ENMIENDAS | SE PUBLICA Enmienda | modificación |
| `270` | **MODIFICA** | **SE MODIFICA** | modificación |
| `271` | MODIFICA el plan publicado por | SE MODIFICA el plan | modificación |
| `272` | MODIFICA determinados preceptos | SE MODIFICAN determinados preceptos | modificación |
| `300` | PUBLICA | SE PUBLICA | publicación |
| `301` | PUBLICA Acuerdo de convalidación | SE PUBLICA Acuerdo de convalidación | publicación |
| `303` | PUBLICA el texto revisado | SE PUBLICA el texto revisado | publicación |
| `330` | **CITA** | — (en posteriores: `-`) | **cita** |
| `331` | EN RELACIÓN con | SE DICTA EN RELACIÓN | cita |
| `400` | ACEPTA | SE ACEPTA | trámite |
| `401` | PRORROGA | SE PRORROGA | trámite |
| `402` | INTERPRETA | SE INTERPRETA | trámite |
| `404` | ACTUALIZA | SE ACTUALIZA | trámite |
| `406` | AMPLÍA | SE AMPLÍA | trámite |
| `407` | **AÑADE** | **SE AÑADE** | modificación |
| `408` | COMPLETA | SE COMPLETA | trámite |
| `420` | APRUEBA | SE APRUEBA | aprobación |
| `421` | AUTORIZA | SE AUTORIZA | trámite |
| `422` | RATIFICA | SE RATIFICA | trámite |
| `426` | TRANSPONE | SE TRANSPONE | UE |
| `427` | TRANSPONE parcialmente | SE TRANSPONE parcialmente | UE |
| `430` | ADHESIÓN | ADHESIÓN | tratado |
| `440` | DE CONFORMIDAD con | SE DICTA DE CONFORMIDAD | desarrollo |
| `470` | DECLARA | SE DECLARA | declaración |
| `480` | DECLARA la vigencia | SE DECLARA la vigencia | declaración |
| `490` | **DESARROLLA** | **SE DESARROLLA** | desarrollo |
| `520` | Conflicto promovido en relación con | Conflicto | TC |
| `530` | Cuestión promovida por supuesta inconstitucionalidad | Cuestión | TC |
| `540` | DISPONE el cumplimiento de la Sentencia | SE DISPONE el cumplimiento de la Sentencia | TC |
| `552` | Recurso promovido contra | Recurso | TC |
| `693` | DICTADA | SE DICTA | TC |
| `694` | Recurso planteado en relación con | Recurso | TC |

Total: **53 códigos** de relación. Los que más nos importan para los 4 briefings del GOAL están **en negrita**.

### 2.7 Parámetros del endpoint de lista

`GET /legislacion-consolidada?from=…&to=…&offset=…&limit=…&query=…`

| Parámetro | Tipo | Default | Descripción |
|---|---|---|---|
| `from` | `DATE` (AAAAMMDD) | la más antigua | Solo normas cuya `fecha_actualizacion` ≥ from |
| `to` | `DATE` (AAAAMMDD) | hoy | Solo normas cuya `fecha_actualizacion` ≤ to |
| `offset` | `int ≥ 0` | `0` | Primer resultado |
| `limit` | `int` | `50` | Máximo de resultados (`-1` = todos) |
| `query` | objeto JSON | vacío | Consulta estructurada (ver abajo) |

Estructura del parámetro `query` (JSON URL-encoded):

```json
{
  "query": {
    "query_string": {"query": "titulo:crisis and (materia@codigo:6658 or materia@codigo:4107)"},
    "range": {"fecha_publicacion": {"gte":"19990101", "lte":"19991231"}}
  },
  "sort": [{"fecha_publicacion": "desc"}, {"departamento": "asc"}]
}
```

Campos buscables en `query_string`: `ambito@codigo`, `departamento@codigo`, `rango@codigo`, `fecha_disposicion`, `numero_oficial`, `titulo`, `fecha_publicacion`, `diario_numero`, `vigencia_agotada`, `estado_consolidacion@codigo`, `materia@codigo`, `texto`. Operadores `and` / `or` / `not` + paréntesis.

### 2.8 Códigos HTTP

| Código | Significado |
|---|---|
| `200` | OK |
| `400` | Error de cliente: parámetro inválido, formato Accept no reconocido, identificador mal formado |
| `403` | Método no permitido (solo `GET`) |
| `404` | Norma o bloque no existe |
| `5xx` | Error del servidor |

**No documentado**: `429` (rate limit). En la práctica se asume throttling silencioso y se diseña con backoff (ver `plans/vision.md` §1.3).

---

## Parte 3 — Volumetría real del corpus

Sondeo binario contra la API hoy 2026-05-27 (`?offset=N&limit=1`):

| offset | Resultado |
|---|---|
| 12 100 | `BOJA-b-2020-90390` (auton. Andalucía) |
| 12 280 | `BOE-A-1887-4896` (norma más antigua sondeada) |
| 12 290 | vacío |
| ≥ 12 295 | vacío |

**Total estimado: ~12 285 normas consolidadas** en todo el corpus (mix de `BOE-A` estatal + boletines autonómicos: `BOA`, `BOJA`, `BOCL`, `BORM`, etc.). Histórico desde **1887**. Volumen muy menor del que sugiere el GOAL.md ("la catálogo es grande"). Esto significa que **todo el grafo cabe en memoria** y un Neo4j single-node basta.

---

## Parte 4 — Ejemplo real completo: Ley 39/2015 (`BOE-A-2015-10565`)

**Petición:**
```bash
curl -H "Accept: application/json" \
  https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/BOE-A-2015-10565/metadatos
```

### 4.1 Respuesta `metadatos` (real, 2026-05-27)

```json
{
  "status": {"code": "200", "text": "ok"},
  "data": [
    {
      "fecha_actualizacion": "20260520T070602Z",
      "identificador": "BOE-A-2015-10565",
      "ambito": {"codigo": "1", "texto": "Estatal"},
      "departamento": {"codigo": "7723", "texto": "Jefatura del Estado"},
      "rango": {"codigo": "1300", "texto": "Ley"},
      "fecha_disposicion": "20151001",
      "numero_oficial": "39/2015",
      "titulo": "Ley 39/2015, de 1 de octubre, del Procedimiento Administrativo Común de las Administraciones Públicas.",
      "diario": "Boletín Oficial del Estado",
      "fecha_publicacion": "20151002",
      "diario_numero": "236",
      "fecha_vigencia": "20161002",
      "estatus_derogacion": "N",
      "estatus_anulacion": "N",
      "vigencia_agotada": "N",
      "estado_consolidacion": {"codigo": "3", "texto": "Finalizado"},
      "url_eli": "https://www.boe.es/eli/es/l/2015/10/01/39",
      "url_html_consolidada": "https://www.boe.es/buscar/act.php?id=BOE-A-2015-10565"
    }
  ]
}
```

**Lectura:**
- Norma de rango Ley (`1300`), emitida por Jefatura del Estado.
- Vigente (`estatus_derogacion=N`, `estatus_anulacion=N`, `vigencia_agotada=N`).
- Consolidación al día (`estado_consolidacion=3`).
- ELI canónico: <https://www.boe.es/eli/es/l/2015/10/01/39>.

### 4.2 Respuesta `analisis` (real, fragmentos)

```bash
curl -H "Accept: application/json" \
  https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/BOE-A-2015-10565/analisis
```

```json
{
  "status": {"code": "200", "text": "ok"},
  "data": [
    {
      "materias": [
        {"materia": {"codigo": "6499", "texto": "Seguridad Social"}}
      ],
      "notas": [
        {"nota": [
          "Entrada en vigor, con la salvedad indicada, el 2 de octubre de 2016.",
          "Efectos para las previsiones indicadas en la disposición final 7: 2 de abril de 2021."
        ]}
      ],
      "referencias": {
        "anteriores": [
          {"anterior": [
            {
              "id_norma": "BOE-A-2011-4117",
              "relacion": {"codigo": "210", "texto": "DEROGA"},
              "texto": "los arts. 4 a 7 de la Ley 2/2011, de 4 de marzo"
            },
            {
              "id_norma": "BOE-A-2009-18358",
              "relacion": {"codigo": "210", "texto": "DEROGA"},
              "texto": ", en la forma indicada, determinados preceptos del Real Decreto 1671/2009, de 6 de noviembre"
            },
            {
              "id_norma": "BOE-A-2007-12352",
              "relacion": {"codigo": "210", "texto": "DEROGA"},
              "texto": ", en la forma indicada, la Ley 11/2007, de 22 de junio"
            }
            // ... 8 anteriores más, todas con codigo 210 = DEROGA
          ]}
        ],
        "posteriores": [
          {"posterior": [
            {
              "id_norma": "BOE-A-2020-10491",
              "relacion": {"codigo": "230", "texto": "SE DEJA SIN EFECTO"},
              "texto": "la modificación de la disposición final 7, en la redacción dada por el Real Decreto-ley 27/2020, de 4 de agosto, por Resolución de 10 de septiembre de 2020"
            },
            {
              "id_norma": "BOE-A-2022-11589",
              "relacion": {"codigo": "270", "texto": "SE MODIFICA"},
              "texto": "art. 77, por Ley 15/2022, de 12 de julio"
            }
            // ... 15 posteriores más; mezcla de SE MODIFICA (270), SE AÑADE (407),
            //     SE DECLARA (470), SE DESARROLLA (490), CITA (330),
            //     SE DICTA DE CONFORMIDAD (440), SE DICTA EN RELACIÓN (331),
            //     SE DEJA SIN EFECTO (230)
          ]}
        ]
      }
    }
  ]
}
```

**Lectura para el grafo:**
- Esta norma **deroga** 11 normas previas (`anteriores` con codigo `210`). Cada par `(BOE-A-2015-10565, codigo=210, anterior)` se traduce en una arista `BOE-A-2015-10565 -[:DEROGA]-> BOE-A-anterior`.
- Esta norma ha sido **modificada/citada/desarrollada** por 17 normas posteriores. Cada par genera una arista en sentido inverso: `BOE-A-posterior -[:MODIFICA|CITA|…]-> BOE-A-2015-10565`.
- Para la briefing 1 ("normas más modificadas"), esta ley aporta 17 a su contador in-degree de modificaciones.
- Para la briefing 4 ("blast radius de Ley 30/1992"), esta ley no aplica directamente (no tiene a la 30/1992 en sus `posteriores`); sin embargo, otras normas vivas que sí la citan se detectan recorriendo el grafo desde `BOE-A-1992-26318`.

### 4.3 Cómo se traduce a tuplas de grafo

Las primeras tres aristas de la Ley 39/2015 quedan:

```cypher
MERGE (n0:Norma {id: "BOE-A-2015-10565"})
SET   n0.rango = "1300", n0.titulo = "Ley 39/2015...",
      n0.vigente = true, n0.fecha_pub = date("2015-10-02")

MERGE (n1:Norma {id: "BOE-A-2011-4117"})
MERGE (n0)-[:DEROGA {codigo: 210,
                      texto: "los arts. 4 a 7 de la Ley 2/2011, de 4 de marzo"}]->(n1)

MERGE (n2:Norma {id: "BOE-A-2009-18358"})
MERGE (n0)-[:DEROGA {codigo: 210,
                      texto: "..., determinados preceptos del Real Decreto 1671/2009..."}]->(n2)

MERGE (n3:Norma {id: "BOE-A-2007-12352"})
MERGE (n0)-[:DEROGA {codigo: 210,
                      texto: "..., la Ley 11/2007, de 22 de junio"}]->(n3)
```

Las 4 briefings de GOAL.md se resuelven con queries Cypher / DuckDB sobre exactamente esta estructura.

---

## Parte 5 — Trampas conocidas (resumen)

1. **`estatus_derogacion` es boolean, no enum** — derogación parcial vive en los códigos `211`–`217` del `analisis`.
2. **Comparar verbos por `codigo`, no por `texto`** — el texto cambia entre voz activa/pasiva.
3. **Case inconsistente** — `"Estatal"` vs `"estatal"`, `"Finalizado"` vs `"finalizado"`. Normalizar a minúsculas en consumo.
4. **JSON `data` puede ser `""` en lugar de `[]`** cuando no hay resultados — defenderlo en el parser.
5. **XML-only en `/texto` y bloques** — para JSON puro hace falta 3+ llamadas por norma.
6. **Imágenes PNG base64 inline** en `<version>` pueden hinchar mucho el payload — filtrar/marcar.
7. **`limit=-1`** descarga TODO en una respuesta — preferir paginación.
8. **`fecha_actualizacion` en UTC** (`Z`); el resto de fechas sin zona horaria.
9. **Versionado interno**: una norma consolidada **no** es un texto único, es un *grafo temporal de versiones por bloque*. Cada `<bloque>` tiene N `<version>` distintas.
10. **Verbos no exhaustivos en documentación PDF**: la verdad la dan las tablas auxiliares `relaciones-anteriores` / `relaciones-posteriores` en tiempo de ejecución, no el PDF estático.

---

## Apéndices útiles

### A.1 Códigos `rango` por familia

- **Constitucionales / supralegales**: `1070`, `1180`
- **Leyes**: `1290` (LO), `1300` (Ley), `1450` (Foral)
- **Con fuerza de ley del Gobierno**: `1310` (RDL), `1320` (R-DL), `1500` (D-L), `1470` (DL auton.)
- **Reglamentos**: `1340` (RD), `1510` (Decreto), `1220` (Reglamento)
- **Inferiores**: `1350` (Orden), `1370` (Resolución), `1410` (Instrucción), `1390` (Circular), `1020` (Acuerdo)

### A.2 Mapeo de tipo ELI

El segmento `{tipo}` de la URL ELI sigue la siguiente convención (no formalmente documentada por el BOE pero verificable):

| Tipo ELI | Rango |
|---|---|
| `co` | Constitución |
| `lo` | Ley Orgánica |
| `l` | Ley |
| `rdl` | Real Decreto-ley |
| `rdlg` | Real Decreto Legislativo |
| `rd` | Real Decreto |
| `o` | Orden |
| `res` | Resolución |
| `ai` | Acuerdo Internacional |

### A.3 Recursos externos relacionados

- Portal ELI español: <https://boe.es/legislacion/eli.php>
- Portal ELI europeo: <https://eur-lex.europa.eu/eli-register/about.html>
- Eurovoc (tesauro de materias UE, complementario al de `materias` del BOE): <https://op.europa.eu/en/web/eu-vocabularies/eurovoc>
- Akoma Ntoso (estándar XML OASIS para textos legislativos, para interoperabilidad futura): <https://www.oasis-open.org/committees/legaldocml/>
