# Estructura del Derecho español y de la API del BOE

Este documento describe **dos cosas**:

1. **Cómo se organiza el ordenamiento jurídico español**: jerarquía de normas, partes internas de un texto legal (libros, títulos, capítulos, artículos, apartados…), y conceptos transversales (vigencia, derogación, anulación, consolidación).
2. **Cómo lo expone la API de datos abiertos del BOE**: bloques, campos exactos con tipo y obligatoriedad, vocabularios controlados, verbos de relación y un ejemplo real completo.

> Datos verificados con `curl` real contra `https://www.boe.es/datosabiertos/api/` los días 2026-05-27 y **2026-05-28** (segunda ronda de verificación: conteo de relaciones, tope de paginación, prueba de concurrencia, ruta de tablas auxiliares y volumen total del corpus), complementado con el PDF oficial `resources/datos_boe.pdf` (*"API para el acceso a la colección de Legislación Consolidada"*, AEBOE, 2 sept. 2025) y con las FAQ oficiales (`/datosabiertos/faq/consolidada.php` y `/datosabiertos/faq/datos-auxiliares.php`).

---

## Parte 0 — Conceptos jurídicos clave (leer primero)

Antes de la mecánica de la API conviene fijar cuatro conceptos que la API codifica y que es fácil confundir.

### 0.1 Vigencia ≠ existencia: por qué una norma derogada sigue consultable

Que una norma **deje de estar vigente** significa que **ya no produce efectos hacia el futuro**, pero su texto **no se borra** del ordenamiento ni del corpus. El resultado de derogar A con B **no es "suma 0"**: A no desaparece, queda como texto histórico no vigente, y el texto *consolidado* refleja el estado actual.

El texto histórico tiene funciones jurídicas reales, no sólo archivísticas:

- **Tempus regit actum** (la razón principal): los hechos se juzgan con la ley vigente *cuando ocurrieron*. Un contrato de 2010, un delito de 2015 o un impuesto devengado en 2018 se resuelven con la norma de aquel momento, aunque hoy esté derogada. Jueces y administraciones necesitan el texto histórico exacto para resolver casos del pasado.
- **Regímenes transitorios**: muchas normas derogadas se siguen aplicando a situaciones nacidas bajo ellas (lo que regulan las disposiciones transitorias).
- **Ultraactividad**: a veces una norma derogada se sigue aplicando un tiempo (p. ej. ciertos convenios colectivos, o cuando la propia norma lo dispone).
- **Interpretación**: entender la ley actual a menudo exige saber qué reemplazó y por qué.
- **Transparencia, investigación y litigios** sobre periodos pasados.

### 0.2 Qué es una norma "consolidada" (y qué no lo es)

El BOE maneja dos artefactos distintos para cada norma:

1. El **texto original publicado** en el diario oficial en su fecha. Es fijo para siempre y es el **texto auténtico** a efectos legales.
2. El **texto consolidado**: una obra editorial de la AEBOE que **integra el texto original + todas sus modificaciones posteriores** en un único documento actualizado y legible, marcando qué cambió, cuándo y por qué norma.

Una **norma consolidada** es aquella para la que la AEBOE mantiene ese texto integrado y versionado. **No todas las normas se consolidan**: sólo un subconjunto curado (la colección `legislacion-consolidada`). Muchas disposiciones menores sólo existen como texto original del diario, sin consolidar.

Dos matices importantes:

- El texto consolidado es **oficial pero no auténtico**: si hubiera discrepancia, prevalece el publicado en el diario. Es una ayuda de accesibilidad, no la fuente legal vinculante. Para citar con rigor jurídico se cita la norma y su publicación, no "el consolidado".
- `estado_consolidacion` mide el **desfase editorial**, no la vigencia: `3 = Finalizado` (el consolidado está al día con todas las modificaciones publicadas) vs `4 = Desactualizado` (hay modificaciones ya publicadas que aún no se han integrado). Una norma puede estar perfectamente vigente y a la vez `Desactualizado`.

### 0.3 Derogación, anulación, vigencia agotada y caducidad de bloque

Cuatro cosas distintas que la API distingue con campos separados:

- **Derogación**: una norma posterior deja sin efecto a otra **hacia el futuro** (ex nunc). Lo hecho bajo la norma derogada sigue siendo válido. Si es **parcial**, sólo se quitan los preceptos derogados; el resto sigue vivo.
- **Anulación**: un órgano competente (típicamente el Tribunal Constitucional) la declara nula, normalmente **desde el origen** (ex tunc) — como si nunca hubiera sido válida, con límites para no reabrir cosa juzgada ni situaciones consolidadas. El efecto práctico se parece a la derogación, pero la lógica temporal es retroactiva.
- **Vigencia agotada**: la norma cumplió su propósito temporal (p. ej. una ley anual de presupuestos) sin necesidad de derogación expresa.
- **Caducidad de un bloque** (`fecha_caducidad`): es un atributo de **presentación**, no de validez jurídica. Marca la fecha a partir de la cual ese bloque deja de mostrarse en el consolidado (p. ej. una disposición transitoria que agotó su función, o una versión superada por otra).

### 0.4 ¿`estatus_derogacion=S` con derogación parcial?

**No.** `estatus_derogacion` es un **booleano sobre la norma entera**. Una derogación de algunos artículos deja la norma viva (`estatus_derogacion=N`) y el matiz "parcial" vive en `referencias.posteriores` con los códigos de derogación parcial `211`–`217` (ver §2.6). Es decir: `estatus_derogacion=S` ⇒ la norma **completa** está derogada.

> ⚠️ El umbral exacto del disparador conviene re-verificarlo empíricamente con una norma de derogación parcial conocida; el PDF sólo dice "indica si la disposición está derogada `[SN]`" sin precisar el criterio.

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

Los **rangos** completos los devuelve `GET /datosabiertos/api/datos-auxiliares/rangos` (Accept: application/json) — son 19 entradas tal cual. *(Ruta confirmada `200` el 2026-05-28; ver §2.1.1.)*

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

**Cómo aparece esta jerarquía en la API (importante):** de forma **semi-estructurada, NO como árbol anidado**. La API devuelve una **lista plana de `<bloque>`**, cada uno con `tipo` y `titulo`. La jerarquía Libro/Título/Capítulo no viene modelada como anidamiento:
- Los encabezados estructurales ("TÍTULO I", "CAPÍTULO II") aparecen como bloques `tipo="encabezado"`.
- Los **artículos vivos** son `tipo="precepto"`.
- Para reconstruir el árbol hay que **inferirlo** del orden de los bloques + el texto del `titulo` + el `tipo`.

El texto crudo de cada artículo vive dentro de `<version>` como HTML (ver §2.5). El `tipo` de bloque toma valores en {`nota_inicial`, `preambulo`, `instrumento`, `parte_dispositiva`, `parte_final`, `encabezado`, `precepto`, `firma`}.

### 1.3 Vida y muerte de una norma (vigencia, derogación, anulación)

Cuatro conceptos distintos que la API distingue con campos separados (su significado jurídico está en §0.3):

| Concepto | Significado | Campo en la API |
|---|---|---|
| **Entrada en vigor** | Cuándo empieza a producir efectos | `fecha_vigencia` (DATE, opcional) |
| **Vigencia agotada** | La norma cumplió su propósito temporal (ej. ley anual de presupuestos) | `vigencia_agotada` (`S`/`N`) |
| **Derogación** | Una norma posterior la deja sin efecto (total o parcial) | `estatus_derogacion` (`S`/`N`) + `fecha_derogacion` |
| **Anulación** | El TC u órgano competente la declara nula desde origen | `estatus_anulacion` (`S`/`N`) + `fecha_anulacion` |

**Importante** (verificado): `estatus_derogacion` **NO es un enum** con valores tipo "vigente / derogada total / derogada parcial". Es **booleano `S`/`N`** referido a la norma **completa** (§0.4). El matiz "derogada parcialmente" hay que extraerlo del bloque `referencias.posteriores` buscando relaciones con `codigo` ∈ {`211`, `212`, `213`, `214`, `215`, `216`, `217`} (ver tabla §2.6).

**Estado de consolidación** (`estado_consolidacion`) son solo **2 valores** (regex de código `[34]`):

| Código | Texto | Significado |
|---|---|---|
| `3` | **Finalizado** | La consolidación está al día con todas las modificaciones publicadas |
| `4` | **Desactualizado** | Hay modificaciones publicadas no integradas todavía en el texto consolidado |

### 1.4 Tipos de relaciones entre normas (los "verbos")

Cuando una norma habla de otra, lo hace con uno de los **50 verbos** (✅ conteo verificado el 2026-05-28: `GET /datos-auxiliares/relaciones-anteriores` devuelve **50** entradas; cualquier afirmación previa de "53" era errónea) documentados en `relaciones-anteriores` / `relaciones-posteriores`. Los **importantes para los 4 briefings del GOAL** son:

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

El catálogo completo (50 códigos) está en la sección §2.6.

---

## Parte 2 — La API del BOE en detalle

### 2.0 Envelope común de respuesta

**Toda** respuesta de la API (lista, metadatos, análisis, texto, índice, bloque) va envuelta en la misma estructura. Conviene tratarla como contrato base antes de mirar cada endpoint.

XML:
```xml
<?xml version="1.0" encoding="utf-8"?>
<response>
  <status>
    <code>200</code>
    <text>ok</text>
  </status>
  <data> ... </data>
</response>
```

JSON:
```json
{ "status": { "code": "200", "text": "ok" }, "data": [ ... ] }
```

- `status.code` / `status.text`: resultado de la operación.
- `data`: el payload. **Defensa obligatoria en el parser**: cuando no hay resultados, `data` puede venir como `<data/>` (XML), `[]`, `{}` o incluso `""` (string vacío) en JSON. No asumir que siempre es un array.

### 2.1 Endpoints (legislación consolidada)

Base: `https://www.boe.es/datosabiertos/api/legislacion-consolidada`. Método siempre `GET` (otro método → `403`). Selección de formato por cabecera HTTP `Accept` (`application/json` o `application/xml`). Sin API key.

| Ruta | Devuelve | JSON | XML |
|---|---|---|---|
| `/legislacion-consolidada` | Lista paginada con `from`/`to`/`offset`/`limit`/`query` | ✅ | ✅ |
| `/legislacion-consolidada/id/{id}` | Norma completa (metadatos + analisis + metadata-eli + texto) | ❌ | ✅ |
| `/legislacion-consolidada/id/{id}/metadatos` | Solo metadatos | ✅ | ✅ |
| `/legislacion-consolidada/id/{id}/analisis` | Solo análisis (materias, notas, referencias) | ✅ | ✅ |
| `/legislacion-consolidada/id/{id}/metadata-eli` | Metadatos ELI | ❌ | ✅ |
| `/legislacion-consolidada/id/{id}/texto` | Texto consolidado completo (todas las versiones) | ❌ | ✅ |
| `/legislacion-consolidada/id/{id}/texto/indice` | Índice (tabla de contenidos) de bloques de la norma | ✅ | ✅ |
| `/legislacion-consolidada/id/{id}/texto/bloque/{id_bloque}` | Un bloque concreto (todas sus versiones) | ❌ | ✅ |

El nodo `<data>` de `/id/{id}` (norma completa) contiene 4 nodos no repetitivos, con esta obligatoriedad:

| Nodo | Descripción | Obl. |
|---|---|---|
| `metadatos` | Metadatos de la norma | `[1..1]` |
| `analisis` | Análisis (materias, notas, referencias) | `[0..1]` |
| `metadata-eli` | Metadatos ELI | `[0..1]` |
| `texto` | Texto consolidado con todas sus versiones | `[1..1]` |

#### 2.1.1 Tablas auxiliares (vocabularios controlados)

> ✅ **Ruta correcta verificada el 2026-05-28: `/datos-auxiliares/*` (`/datos-auxiliares/rangos` → `200`).** La variante `/tablas-auxiliares/*` devuelve `404` (es un bug del cliente `ComputingVictor/MCP-BOE`, no usarla). Las tablas **se actualizan a diario** (FAQ oficial). La verdad sobre los códigos la dan estas tablas en tiempo de ejecución, no el PDF estático.

Base: `https://www.boe.es/datosabiertos/api/datos-auxiliares`.

| Ruta | Contenido | Tamaño aprox. |
|---|---|---|
| `/datos-auxiliares/rangos` | 19 niveles normativos | ~500 B |
| `/datos-auxiliares/estados-consolidacion` | 2 estados | ~84 B |
| `/datos-auxiliares/ambitos` | Estatal / autonómico | pequeño |
| `/datos-auxiliares/departamentos` | ~70 organismos emisores | ~10 KB |
| `/datos-auxiliares/materias` | ~1300 materias jurídicas | ~337 KB |
| `/datos-auxiliares/relaciones-anteriores` | **50** verbos en voz activa (verificado) | ~1.4 KB |
| `/datos-auxiliares/relaciones-posteriores` | **50** verbos en voz pasiva (verificado) | ~1.4 KB |

La tabla `departamentos` es común a la API de Legislación consolidada y a la API del BOE; cubre un ámbito temporal muy amplio, por lo que puede haber registros sin ocurrencias en alguna de las dos.

### 2.2 Bloque `metadatos`

Formato de salida: XML, JSON. La columna **Regex/Formato** recoge el patrón oficial del PDF (corregido donde procede).

| Campo | Tipo | Regex / Formato | Obligatorio | Descripción |
|---|---|---|---|---|
| `identificador` | `CHAR(20)` | Estatal: `BOE-[A-Z]-\d{4}-\d{1,5}`. **General (incl. autonómicos): `[A-Z]{3,4}-[A-Za-z]-\d{4}-\d{1,6}`** | ✅ | Clave primaria. Ej. estatal `BOE-A-2015-10565`; autonómico `BOJA-b-2020-90390`. ⚠ El regex del PDF (`[A-Z]{3}-[A-Z]-\d{4}-\d{1,5}`) sólo cubre `BOE-A-*`: los boletines autonómicos usan prefijo de 3-4 letras y **letra separadora en minúscula** |
| `fecha_actualizacion` | `TIME` | `\d{14}Z` → `AAAAMMDDTHHmmSSZ` (UTC) | ✅ | Última vez que la AEBOE tocó esta consolidada — clave para ingesta incremental. Único campo en UTC con `Z` |
| `ambito.codigo` / `ambito.texto` | `NUMBER` / `CHAR(20)` | `\d{1}` ; `1`=Estatal, `2`=Autonómica | ✅ | Ámbito territorial |
| `departamento.codigo` / `departamento.texto` | `NUMBER` / `CHAR(100)` | `\d+` ; p.ej. `7723`=Jefatura del Estado | ✅ | Órgano emisor |
| `rango.codigo` / `rango.texto` | `NUMBER` / `CHAR(100)` | `\d+` ; ver tabla §1.1 | ✅ | Nivel normativo |
| `titulo` | `CHAR(4000)` | — | ✅ | Título oficial |
| `numero_oficial` | `CHAR(20)` | `39/2015`, `JUS/987/2020`, `PCM/997/2022` | ⚪ | Numeración oficial publicada |
| `diario` | `CHAR(200)` | "Boletín Oficial del Estado" | ✅ | Diario oficial — casi constante para ámbito estatal |
| `diario_numero` | `NUMBER` | `\d+` | ✅ | Número del diario donde se publicó |
| `fecha_disposicion` | `DATE` | `\d{8}` → `AAAAMMDD` | ⚪ | Fecha de aprobación |
| `fecha_publicacion` | `DATE` | `\d{8}` → `AAAAMMDD` | ✅ | Fecha de publicación en el BOE |
| `fecha_vigencia` | `DATE` | `\d{0,8}` (puede ser vacío) | ⚪ | Entrada en vigor |
| `estatus_derogacion` | `CHAR(1)` | `[SN]` | ✅ | ¿Derogada la norma completa? (boolean) |
| `fecha_derogacion` | `DATE` | `\d{0,8}` (vacío si N) | ⚪ | Fecha en que se derogó |
| `estatus_anulacion` | `CHAR(1)` | `[SN]` | ✅ | ¿Anulada? (boolean) |
| `fecha_anulacion` | `DATE` | `\d{0,8}` | ⚪ | Fecha de anulación |
| `vigencia_agotada` | `CHAR(1)` | `[SN]` | ✅ | ¿Vigencia agotada por cumplimiento del fin? |
| `estado_consolidacion.codigo` / `.texto` | `NUMBER` / `CHAR(100)` | `[34]` ; `3`=Finalizado, `4`=Desactualizado | ✅ | Estado de la consolidación |
| `url_eli` | `CHAR(150)` | `https://www.boe.es/eli/es/{tipo}/{AAAA}/{MM}/{DD}/{numero}` | ⚪ | Permalink ELI |
| `url_html_consolidada` | `CHAR(150)` | `https://www.boe.es/buscar/act.php?id={id}` | ✅ | URL HTML legible — reconstruible desde `identificador` |

**Por qué hay campos opcionales (`⚪` / `[0..1]`):** no es que sea opcional pedirlos, es que **el campo puede no existir** para esa norma y entonces no se incluye. Una norma del siglo XIX puede carecer de `numero_oficial` o `fecha_disposicion`; `fecha_vigencia` puede ser desconocida; `fecha_derogacion`/`fecha_anulacion` sólo existen si la norma fue derogada/anulada; `url_eli` sólo si se acuñó un ELI.

**Tipos lógicos (deducidos):**
- `CHAR(N)` = string UTF-8 de longitud máxima N.
- `NUMBER` = entero positivo.
- `DATE` = string `\d{0,8}` (puede estar vacío).
- `TIME` = string `\d{14}Z` siempre presente.

> Nota de obligatoriedad: la respuesta del **endpoint de lista** (`/legislacion-consolidada`) NO incluye `estatus_derogacion`, `fecha_derogacion`, `estatus_anulacion` ni `fecha_anulacion`; esos cuatro sólo aparecen en `/metadatos`. La lista sí incluye el resto de campos de la tabla.

### 2.3 Bloque `analisis`

Formato de salida: XML, JSON. Estructura general:

```
analisis
  ├── materias[]
  ├── notas[]
  └── referencias
       ├── anteriores[]   ← lo que esta norma hace a normas previas
       └── posteriores[]  ← lo que normas posteriores le han hecho a esta
```

Los tres subnodos son opcionales (`[0..1]`), sólo aparecen si tienen contenido.

#### 2.3.1 `materias[]`

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `materia.codigo` | `NUMBER` | ✅ | Código de materia (vocabulario controlado de ~1300 entradas) |
| `materia.texto` | `CHAR(256)` | ✅ | Descripción legible. Ej.: `Adopción`, `Seguridad Social` |

*(Corregido: el PDF especifica `CHAR(256)`, no `CHAR(200)`.)*

#### 2.3.2 `notas[]`

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `nota` | `array<CHAR(1500)>` | ✅ | Notas en texto libre |

**Qué contienen y por qué importan:** texto editorial de la AEBOE — caveats de entrada en vigor ("entrada en vigor, con la salvedad indicada, el 2 de octubre de 2016"), efectos escalonados de ciertas disposiciones ("efectos para las previsiones de la D.F. 7: 2 de abril de 2021"), en qué números del diario se publicó, correcciones aplicadas. **Son información jurídica real** cuando hay entrada en vigor diferida o efectos por disposición; para RAG son contexto valioso, para el grafo metadato.

#### 2.3.3 `referencias.anteriores[]` y `referencias.posteriores[]`

Mismo esquema, solo cambia la voz del verbo (activa vs pasiva).

| Campo | Tipo | Obligatorio | Descripción |
|---|---|---|---|
| `id_norma` | `CHAR(20)` | ✅ | Identificador de la otra norma |
| `relacion.codigo` | `NUMBER` | ✅ | Código del verbo (tabla §2.6) |
| `relacion.texto` | `CHAR(256)` | ✅ | Verbo en lenguaje natural. ⚠ El **texto cambia** entre anteriores (`DEROGA`) y posteriores (`SE DEROGA`); el `codigo` **no cambia** |
| `texto` | `CHAR(1500)` | ⚪ | Texto libre que precisa el alcance. Ej.: `"los arts. 4 a 7 de la Ley 2/2011, de 4 de marzo"` |

**Regla de oro**: para construir el grafo, **siempre comparar por `relacion.codigo`**, nunca por `relacion.texto`.

**El `texto` NO es redundante con `relacion`** — hay que atender a ambos: `relacion.codigo` da el **tipo** de relación (DEROGA/MODIFICA/AÑADE…); el `texto` da el **alcance** (qué precepto: "los arts. 4 a 7", "la disposición adicional 8") y el **instrumento** ("por Ley 15/2022, de 12 de julio"). Para un grafo preciso necesitas el código para el tipo de arista y el texto para saber qué artículo concreto se tocó.

### 2.4 Bloque `metadata-eli`

Solo XML. Contiene metadatos siguiendo la ontología **ELI** (European Legislation Identifier, estándar W3C/UE).

**Qué es ELI:** (a) un esquema de **URI estable y legible** para citar legislación de forma uniforme en toda la UE — `https://www.boe.es/eli/es/l/2015/10/01/39` codifica país/tipo/año/mes/día/número; y (b) una **ontología de metadatos en RDF** para que sistemas de distintos países interoperen. Para el alcance de Reversa, el `url_eli` que ya viene en `metadatos` basta como clave canónica cruzable con EUR-Lex; el nodo `<metadata-eli>` completo sólo hace falta si se va a publicar Linked Data.

Referencias oficiales:
- <https://boe.es/legislacion/eli.php>
- <https://elidata.es>

### 2.5 Bloque `texto`

Solo XML. Es el corazón del contenido normativo. Tres definiciones clave:

- **`texto`** = el texto consolidado completo de la norma, con todo su historial.
- **`<bloque>`** = una unidad estructural (un artículo, una disposición, el preámbulo, la firma, un anexo), con `id`, `tipo` y `titulo`.
- **`<version>`** = una **foto temporal** del contenido de ese bloque. Un bloque tiene **≥1 versiones** porque su redacción cambia cada vez que una norma lo modifica.

```xml
<texto>
  <bloque id="a21" tipo="precepto" titulo="Artículo 21. Obligación de resolver"
          [fecha_caducidad="AAAAMMDD"]>
    <version fecha_publicacion="20151002" fecha_vigencia="20161002"
             id_norma="BOE-A-2015-10565">
      <p class="..."> ...redacción original... </p>
    </version>
    <version fecha_publicacion="20220713"
             id_norma="BOE-A-2022-11589">
      <p class="..."> ...redacción modificada (vigente)... </p>
    </version>
  </bloque>
  ...
</texto>
```

Atributos de `<bloque>`:

| Atributo | Tipo | Obl. | Valores |
|---|---|---|---|
| `id` | `CHAR(100)` | `[1..1]` | Identificador del bloque, usado en `/texto/bloque/{id_bloque}` |
| `tipo` | `CHAR(50)` | `[1..1]` | `nota_inicial`, `preambulo`, `instrumento`, `encabezado`, `parte_dispositiva`, `precepto`, `parte_final`, `firma` |
| `titulo` | `CHAR(4000)` | `[1..1]` | Ej.: `Artículo 21. Obligación de resolver` |
| `fecha_caducidad` | `DATE` | `[0..1]` | Si está, el bloque deja de mostrarse a partir de esa fecha (presentación, no validez) |

Atributos de `<version>`:

| Atributo | Tipo | Obl. | Valores |
|---|---|---|---|
| `fecha_publicacion` | `DATE` | `[1..1]` | Fecha de publicación de la norma modificadora (o la inicial) |
| `fecha_vigencia` | `DATE` | `[0..1]` | Entrada en vigor de esta versión |
| `id_norma` | `CHAR(20)` | `[1..1]` | BOE-A de la norma que introdujo esta versión |

#### 2.5.1 ¿La versión actual ya trae el texto modificado? Sí, y cuál quedarse

Cuando una norma modificadora cambia, p. ej., el artículo 77, la AEBOE **añade una nueva `<version>` a ese bloque** con la redacción nueva (la vigente), etiquetada con `fecha_publicacion`, `fecha_vigencia` e `id_norma` de la norma modificadora. El bloque va **acumulando versiones**: original + una por cada modificación.

- **Texto vigente hoy** = por cada bloque, la versión con `fecha_vigencia` más reciente que sea ≤ hoy y no caducada. Ensamblando la versión vigente de todos los bloques se obtiene el consolidado actual.
- **Texto a una fecha pasada** = la versión que estuviera en vigor en esa fecha.
- Si un artículo fue **derogado**, su bloque puede terminar con una versión que lo marque como suprimido o llevar `fecha_caducidad`.

Conclusión: una norma consolidada **no** es un texto único, es un **grafo temporal de versiones por bloque**. No te quedes con la primera versión (es la redacción original, a menudo superada).

#### 2.5.2 Contenido HTML dentro de `<version>`

Cada `<version>` contiene el texto del bloque en HTML. Debe existir **al menos uno** de estos elementos (no puede haber `<version>` vacía):

| Elemento | Obl. | Qué es | Relevancia para RAG/grafo |
|---|---|---|---|
| `<p class="…">` | `[0..N]` | Párrafo de texto; `class` da el rol CSS (`articulo`, `parrafo`, `nota_pie`…) | 🔴 Esencial — es el cuerpo jurídico |
| `<table>` | `[0..N]` | Tabla HTML estándar | 🔴 Esencial cuando aparece — suele llevar contenido sustantivo (tarifas, baremos, escalas) |
| `<img>` | `[0..N]` | Imagen PNG en base64 inline (siempre PNG: fórmulas, diagramas, mapas, organigramas, firmas) | 🟡 La menos útil para texto y la que más infla el payload; pero a veces es jurídicamente vinculante (una fórmula, un mapa de deslindes). Extraer/marcar aparte, no meter en el embedding |
| `<blockquote>` | `[0..N]` | Nota informativa con HTML anidado ("Se modifica la circunstancia 4ª por…") | 🟢 Procedencia/metadato de cambios, no el texto de la ley. Útil para trazar historial; separar del contenido normativo |

#### 2.5.3 Obtención del índice — `/texto/indice`

Formato de salida: **XML, JSON**. Parámetro `{id}`: identificador de la norma (`{id}` incorrecto → `404`, `data` vacío).

**Qué es:** la **tabla de contenidos de la norma entera** — una lista de bloques con su `id`, `titulo`, fecha y la URL para traer cada uno. Es **uno por norma, NO uno por bloque**: cada bloque no tiene índice propio; el índice es la guía que dice qué bloques hay y cómo pedirlos.

> ⚠️ **`id_bloque` se obtiene del índice, NUNCA se infiere.** Lo dice la FAQ oficial. Las convenciones observadas (`pr` preámbulo, `a1` artículo 1, `dd` disposición derogatoria, `df` disposición final, `fi` firma, `an` anexo, `no` nota inicial) son **pistas, no contrato**: hay `bis`/`ter`, anexos múltiples y numeraciones irregulares. Construir la URL de un bloque adivinando el id da `404`.

> ⚠️ **Trampa de formato:** el `fecha_actualizacion` del índice viene en `AAAAMMDD` (DATE sin hora), **distinto** del `AAAAMMDDTHHmmSSZ` (UTC) de `metadatos`. Mismo nombre, formato distinto según endpoint.

Campos de cada entrada del índice:

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | `CHAR(100)` | Identificador del bloque (para `/texto/bloque/{id_bloque}`) |
| `titulo` | `CHAR(4000)` | Título del bloque (p. ej. `Artículo 1`, `[preambulo]`, `ANEXO`) |
| `fecha_actualizacion` | `DATE` (`AAAAMMDD`) | Fecha de la última actualización del bloque |
| `url` | `CHAR(200)` | URL absoluta del bloque |

Ejemplo (JSON-equivalente):
```json
{ "status": {"code":"200","text":"ok"},
  "data": [
    {"id":"pr","titulo":"[preambulo]","fecha_actualizacion":"20200718",
     "url":"https://www.boe.es/datosabiertos/api/legislacion-consolidada/id/BOE-A-2020-8099/texto/bloque/pr"},
    {"id":"a1","titulo":"Artículo 1","fecha_actualizacion":"20220915", "url":"...bloque/a1"}
  ]
}
```

#### 2.5.4 Obtención de un bloque — `/texto/bloque/{id_bloque}`

Formato de salida: **XML**. Parámetros: `{id}` (norma) e `{id_bloque}` (del índice). Devuelve un `<bloque>` con **todas sus versiones**. `{id}` mal formado → `400`; norma o bloque inexistente → `404` (con `data` vacío en ambos casos).

### 2.6 Catálogo completo de verbos de relación

Salida verbatim de `GET /datos-auxiliares/relaciones-anteriores` y `…/relaciones-posteriores`. ✅ **Conteo verificado: 50 códigos** (2026-05-28).

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
| `330` | **CITA** | — | **cita** |
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

Total: **50 códigos** de relación (verificado). Los más relevantes para los 4 briefings del GOAL están **en negrita**.

> ⚠️ Si el endpoint vivo devolviera un número distinto de 50 en el futuro, esta tabla manda menos que la respuesta en tiempo de ejecución: las tablas auxiliares se actualizan a diario.

### 2.7 Parámetros del endpoint de lista

`GET /legislacion-consolidada?from=…&to=…&offset=…&limit=…&query=…`

| Parámetro | Tipo | Default | Descripción |
|---|---|---|---|
| `from` | `DATE` (AAAAMMDD) | la más antigua | Solo normas cuya `fecha_actualizacion` ≥ from |
| `to` | `DATE` (AAAAMMDD) | hoy | Solo normas cuya `fecha_actualizacion` ≤ to |
| `offset` | `int ≥ 0` | `0` | Primer resultado |
| `limit` | `int` | `50` | Máximo de resultados (`-1` = "todos", **pero topado a 10.000 por respuesta**, ver abajo) |
| `query` | objeto JSON | vacío | Consulta estructurada (ver abajo) |

Orden por defecto de la lista: **`fecha_actualizacion` descendente** (los más recientemente actualizados primero; por eso los autonómicos, más nuevos en la colección, salen en la cola).

> ⚠️ **Tope de 10.000 (verificado 2026-05-28).** `limit=-1` devuelve como máximo **10.000** ítems por respuesta, independientemente del tamaño real del corpus. **Hay que paginar con `offset`** para recorrerlo entero (ver §3).

#### 2.7.1 El parámetro `query` es un DSL estilo Elasticsearch (NO MongoDB)

La consulta estructurada usa la sintaxis **query_string de Elasticsearch / Lucene**, no la de MongoDB. Estructura (JSON URL-encoded):

```json
{
  "query": {
    "query_string": {"query": "titulo:crisis AND (materia@codigo:6658 OR materia@codigo:4107)"},
    "range": {"fecha_publicacion": {"gte":"19990101", "lte":"19991231"}}
  },
  "sort": [{"fecha_publicacion": "desc"}, {"departamento": "asc"}]
}
```

- **`query_string.query`**: sintaxis Lucene — parejas `campo:valor` unidas por `AND` / `OR` / `NOT`, con paréntesis para agrupar, comillas para frase exacta (`titulo:"código penal"`) y agrupación de términos (`titulo:(crisis economica)`).
- **`range`**: filtros por rango. **Restringido a campos de tipo fecha** (`fecha_publicacion`, `fecha_disposicion`…), formato ISO 8601; se puede omitir `gte` o `lte`. Usar `range` sobre un campo no-fecha da error.
- **`sort`**: array de `{"campo":"asc|desc"}` (`asc` por defecto). Se puede ordenar por cualquier campo de la respuesta.

Campos buscables en `query_string`: `ambito@codigo`, `departamento@codigo`, `rango@codigo`, `fecha_disposicion`, `numero_oficial`, `titulo`, `fecha_publicacion`, `diario_numero`, `vigencia_agotada`, `estado_consolidacion@codigo`, `materia@codigo`, `texto`. (`texto` = búsqueda full-text en todo el articulado; `materia@codigo` = búsqueda por temática del vocabulario controlado.)

### 2.8 Códigos HTTP

| Código | Significado |
|---|---|
| `200` | OK (incluso búsqueda sin resultados: `data` vacío) |
| `400` | Error de cliente: parámetro inválido, formato `Accept` no reconocido, identificador mal formado. Mensajes textuales típicos abajo |
| `403` | Método no permitido (solo `GET`) |
| `404` | Norma o bloque no existe |
| `503` | **Servicio no disponible / sobrecarga** — aparece bajo concurrencia alta (ver §3.1). Tratar como transitorio con backoff |
| `5xx` | Error del servidor |

Mensajes `400` textuales (útiles para matching en el parser):
- `El parámetro <<nombre>> debe ser un número`
- `El parámetro <<nombre>> debe ser un entero`
- `El parámetro <<nombre>> de tipo <<tipo>> no ha sido especificado siendo obligatorio`
- `El parámetro <<nombre>> de tipo query no ha sido especificado siendo obligatorio`
- `No reconocido el formato de la cabecera Accept`
- `No soportado ningún mime type de la cabecera Accept`
- Búsqueda (`/legislacion-consolidada`): `Search error: <<mensaje>>`
- Norma concreta (`/id/{id}`): `Identificador no válido o parámetros incorrectos`

> **No documentado oficialmente:** `429` (rate limit por cuota). En la práctica la API no devuelve `429` sino `503` cuando se la satura (ver §3.1). Diseñar con backoff exponencial igualmente.

---

## Parte 3 — Volumetría real y límites operativos del corpus

✅ **Total verificado el 2026-05-28: 12.282 normas consolidadas** (recorrido completo paginando con `offset`, sumando tandas). La estimación previa de ~12.285 era correcta; la cifra de "50.000" que circula en el repo `MCP-BOE` es **errónea**.

El corpus es un mix de `BOE-A` estatal + boletines autonómicos consolidados (`BOJA` Andalucía, `BORM` Murcia, `BOA` Aragón, `BOCL` Castilla y León, etc.). **Incluye legislación autonómica** (confirmado: `BOJA-b-2020-90390` aparece cerca del final de la lista, offset ~12.100). Como la lista va ordenada por `fecha_actualizacion` descendente, los autonómicos son una **minoría reciente** en la cola, no el grueso. Histórico desde **1887**.

Desglose por prefijo (ejecutar para el dato exacto, cubriendo ambos tramos por el tope de 10.000):
```bash
for off in 0 10000; do
  curl -s -H "Accept: application/json" \
   "https://www.boe.es/datosabiertos/api/legislacion-consolidada?limit=-1&offset=$off" \
   | python3 -c "import sys,json,collections;d=json.load(sys.stdin)['data'];print(collections.Counter(x['identificador'].split('-')[0] for x in d))"
done
```

Como ~12.282 normas caben en memoria, **todo el grafo cabe en un Neo4j single-node**.

### 3.1 Paginación obligatoria y límite de concurrencia (prueba de estrés)

**Paginación.** `limit=-1` topa en 10.000 por respuesta, así que el censo completo exige recorrer con `offset`:

```bash
total=0; off=0
while :; do
  n=$(curl -s -H "Accept: application/json" \
    "https://www.boe.es/datosabiertos/api/legislacion-consolidada?offset=$off&limit=-1" \
    | python3 -c "import sys,json;print(len(json.load(sys.stdin)['data']))")
  [ "$n" -eq 0 ] && break
  total=$((total+n)); off=$((off+n)); echo "offset=$off acumulado=$total"
  sleep 0.3
done
echo "TOTAL=$total"   # → 12282 el 2026-05-28
```

**Concurrencia (prueba de estrés real, 50 peticiones en paralelo, 2026-05-28).** Patrón observado:

| Tanda aproximada | Resultado | Latencia |
|---|---|---|
| ~10 primeras | `200` | 0,15 – 0,35 s |
| ~7 siguientes | `200` | ~1,3 s |
| ~7 siguientes | `200` | ~3,3 s |
| resto (~26) | **`503`** | ~5,2 s (constante) |

Lectura: el servidor admite del orden de **~10 conexiones concurrentes cómodas**, encola las siguientes (latencia creciente) y a partir de un umbral las **rechaza con `503` tras ~5 s** (timeout/limite de cola, no rate-limit de cuota: por eso `503` y no `429`).

**Guía de ingesta:**
- Concurrencia máxima **~5–8 peticiones en vuelo**.
- **Backoff exponencial con jitter** ante `503` y reintentar (es transitorio).
- Para decenas de miles de objetos (12.282 normas × varios endpoints cada una) asumir un *crawl* educado de **horas**, no un sprint.

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

### 4.4 Notación de obligatoriedad `[n..m]`

El PDF y este documento usan cardinalidad UML para indicar ocurrencias:

| Notación | Significado |
|---|---|
| `[1..1]` | Exactamente uno (obligatorio y único) |
| `[0..1]` | Cero o uno (opcional, único) |
| `[1..N]` | Uno o muchos (obligatorio, repetible) |
| `[0..N]` | Cero o muchos (opcional, repetible) |

El primer número es el mínimo de ocurrencias; el segundo, el máximo. Un campo `[0..1]` "no obligatorio" no significa que sea opcional pedirlo, sino que **puede no existir** y entonces no se incluye en la respuesta.

---

## Parte 5 — Trampas conocidas (resumen)

1. **`estatus_derogacion` es boolean de la norma completa, no enum** — derogación parcial vive en los códigos `211`–`217` del `analisis`; con derogación parcial el flag sigue en `N`.
2. **Comparar verbos por `codigo`, no por `texto`** — el texto cambia entre voz activa/pasiva. El `texto` libre de cada referencia NO es redundante: da el alcance (qué artículo) y el instrumento (qué norma).
3. **Case inconsistente** — `"Estatal"` vs `"estatal"`, `"Finalizado"` vs `"finalizado"`. Normalizar a minúsculas en consumo.
4. **`data` puede venir vacío como `""`, `[]` o `{}`** (no solo array) cuando no hay resultados — defenderlo en el parser.
5. **XML-only en `/texto`, `/texto/bloque/{id_bloque}`, `/id/{id}` (completa) y `/metadata-eli`** — para JSON puro hace falta combinar `/metadatos`, `/analisis` y `/texto/indice` (este último sí da JSON).
6. **Imágenes PNG base64 inline** en `<version>` pueden inflar mucho el payload — filtrar/marcar; siempre son PNG.
7. **`limit=-1` topa en 10.000 por respuesta** — paginar con `offset` para el censo completo (§3.1).
8. **Concurrencia ~10; por encima degrada y devuelve `503` a ~5 s** — limitar a 5-8 en vuelo + backoff (§3.1).
9. **`fecha_actualizacion` está en UTC (`Z`) en `metadatos`, pero en `AAAAMMDD` (sin hora) en `/texto/indice`** — mismo nombre, formato distinto. El resto de fechas van sin zona horaria.
10. **Versionado interno**: una norma consolidada **no** es un texto único, es un *grafo temporal de versiones por bloque*. Cada `<bloque>` tiene N `<version>`; para el texto vigente, quedarse con la versión en vigor más reciente por bloque.
11. **`id_bloque` se obtiene de `/texto/indice`, no se infiere** — las convenciones (`pr`, `a1`, `dd`…) son pistas, no contrato.
12. **El `query` es DSL Elasticsearch/Lucene, no MongoDB** — `range` solo aplica a campos fecha.
13. **Verbos / tablas auxiliares no exhaustivos en el PDF**: la verdad la dan `/datos-auxiliares/*` en tiempo de ejecución (50 relaciones hoy), no el PDF estático. Ruta correcta `/datos-auxiliares/*`; `/tablas-auxiliares/*` da `404`.
14. **El regex de `identificador` del PDF solo cubre `BOE-A-*`**: los autonómicos (`BOJA-b-…`) tienen 3-4 letras de prefijo y separador en minúscula.

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

- Portal de datos abiertos AEBOE: <https://www.boe.es/datosabiertos/api/api.php>
- FAQ Legislación consolidada: <https://www.boe.es/datosabiertos/faq/consolidada.php>
- FAQ Datos auxiliares: <https://www.boe.es/datosabiertos/faq/datos-auxiliares.php>
- Portal ELI español: <https://boe.es/legislacion/eli.php>
- Portal ELI europeo: <https://eur-lex.europa.eu/eli-register/about.html>
- Eurovoc (tesauro de materias UE, complementario al de `materias` del BOE): <https://op.europa.eu/en/web/eu-vocabularies/eurovoc>
- Akoma Ntoso (estándar XML OASIS para textos legislativos, para interoperabilidad futura): <https://www.oasis-open.org/committees/legaldocml/>
