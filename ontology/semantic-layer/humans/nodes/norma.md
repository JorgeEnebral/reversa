# :Norma

Nodo principal del grafo. Una norma consolidada del boletín oficial.

| Atributo | Tipo | Obligatorio | Descripción | Ejemplo |
|---|---|---|---|---|
| id | string | sí | Identificador del boletín oficial (e.g. BOE-A-2015-10565) | `BOE-A-2015-10565` |
| rango_codigo | int | no | Código del rango normativo | `1300` |
| rango | string | no | Texto del rango (e.g. Ley, Real Decreto) | `Ley` |
| fecha_disposicion | string | no | Fecha de disposición YYYY-MM-DD | `2015-10-01` |
| numero_oficial | string | no | Número oficial de la norma | `39/2015` |
| titulo | string | no | Título oficial de la norma | `Ley 39/2015, de 1 de octubre, del Procedimiento Administrativo Común` |
| fecha_publicacion | string | no | Fecha de publicación en el boletín YYYY-MM-DD | `2015-10-02` |
| fecha_vigencia | string | no | Fecha de entrada en vigor YYYY-MM-DD | `2015-10-02` |
| estatus_derogacion | string | no | S/N — norma derogada | `N` |
| fecha_derogacion | string | no | Fecha de derogación YYYY-MM-DD | `2022-05-18` |
| estatus_anulacion | string | no | S/N — norma judicialmente anulada | `N` |
| fecha_anulacion | string | no | Fecha de anulación YYYY-MM-DD | `2022-05-18` |
| vigencia_agotada | string | no | S/N — vigencia agotada por cumplimiento de plazo | `N` |
| vigente | bool | no | Calculado: true si estatus_derogacion=N AND estatus_anulacion=N AND vigencia_agotada=N | `true` |
| estado_consolidacion_codigo | int | no | Código del estado de consolidación | `3` |
| estado_consolidacion | string | no | Texto del estado de consolidación | `Finalizado` |
