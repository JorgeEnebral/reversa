# :Norma

Nodo principal del grafo. Una norma consolidada del BOE.

| Atributo | Tipo | Obligatorio | Descripción | Ejemplo |
|---|---|---|---|---|
| id | string | sí | Identificador BOE | `BOE-A-2015-10565` |
| vigente | bool | no | Calculado: derogacion=N AND anulacion=N AND vigencia_agotada=N | `true` |
| fecha_actualizacion | string | no | Fecha de última actualización ISO-8601 | `20251201T120000Z` |
| ambito_codigo | int | no | Código del ámbito territorial | `1` |
| ambito | string | no | Texto del ámbito territorial | `Estatal` |
| titulo | string | no | Título oficial de la norma | `Ley 39/2015...` |
| diario | string | no | Nombre del boletín oficial | `Boletín Oficial del Estado` |
| departamento_codigo | int | no | Código del departamento emisor | `3681` |
| departamento | string | no | Nombre del departamento emisor | `Jefatura del Estado` |
| rango_codigo | int | no | Código del rango normativo | `1300` |
| rango | string | no | Texto del rango normativo | `Ley` |
| fecha_disposicion | string | no | Fecha de disposición (YYYY-MM-DD) | `2015-10-01` |
| fecha_publicacion | string | no | Fecha de publicación en BOE (YYYY-MM-DD) | `2015-10-02` |
| fecha_vigencia | string | no | Fecha de entrada en vigor (YYYY-MM-DD) | `2015-10-02` |
| estatus_derogacion | string | no | S/N — norma derogada | `N` |
| estatus_anulacion | string | no | S/N — norma judicialmente anulada | `N` |
| vigencia_agotada | string | no | S/N — vigencia agotada | `N` |
| materias_codigos | int[] | no | Códigos de materias temáticas | `[1270, 1680]` |
| materias | string[] | no | Textos de materias temáticas | `["Administración Pública"]` |
