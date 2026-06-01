# :Norma

Nodo principal del grafo. Una norma consolidada del boletín oficial.

| Atributo | Tipo | Obligatorio | Descripción | Ejemplo |
|---|---|---|---|---|
| id | string | sí | Identificador del boletín oficial (e.g. BOE-A-2015-10565) | `BOE-A-2015-10565` |
| fecha_actualizacion | string | no | Fecha de última actualización ISO-8601 | `20251201T120000Z` |
| ambito_codigo | int | no | Código del ámbito territorial (1=Estatal, 2=Autonómico…) | `1` |
| ambito | string | no | Texto del ámbito territorial (e.g. Estatal) | `Estatal` |
| departamento_codigo | int | no | Código del departamento emisor | `3681` |
| departamento | string | no | Nombre del departamento emisor | `Jefatura del Estado` |
| rango_codigo | int | no | Código del rango normativo | `1300` |
| rango | string | no | Texto del rango (e.g. Ley, Real Decreto) | `Ley` |
| fecha_disposicion | string | no | Fecha de disposición YYYY-MM-DD | `2015-10-01` |
| numero_oficial | string | no | Número oficial de la norma | `39/2015` |
| titulo | string | no | Título oficial de la norma | `Ley 39/2015, de 1 de octubre, del Procedimiento Administrativo Común` |
| diario | string | no | Nombre del boletín oficial | `Boletín Oficial del Estado` |
| fecha_publicacion | string | no | Fecha de publicación en el boletín YYYY-MM-DD | `2015-10-02` |
| diario_numero | int | no | Número del boletín oficial | `236` |
| fecha_vigencia | string | no | Fecha de entrada en vigor YYYY-MM-DD | `2015-10-02` |
| estatus_derogacion | string | no | S/N — norma derogada | `N` |
| fecha_derogacion | string | no | Fecha de derogación YYYY-MM-DD | `2022-05-18` |
| estatus_anulacion | string | no | S/N — norma judicialmente anulada | `N` |
| fecha_anulacion | string | no | Fecha de anulación YYYY-MM-DD | `2022-05-18` |
| vigencia_agotada | string | no | S/N — vigencia agotada por cumplimiento de plazo | `N` |
| vigente | bool | no | Calculado: true si estatus_derogacion=N AND estatus_anulacion=N AND vigencia_agotada=N | `true` |
| estado_consolidacion_codigo | int | no | Código del estado de consolidación | `3` |
| estado_consolidacion | string | no | Texto del estado de consolidación | `Finalizado` |
| url_eli | string | no | URL ELI de la norma | `https://www.boe.es/eli/es/l/2015/10/01/39` |
| url_html_consolidada | string | no | URL HTML de la versión consolidada | `https://www.boe.es/buscar/act.php?id=BOE-A-2015-10565` |
| materias_codigos | int[] | no | Códigos de materias temáticas | `[1270, 1680]` |
| materias | string[] | no | Textos de materias temáticas | `["Administración Pública"]` |
