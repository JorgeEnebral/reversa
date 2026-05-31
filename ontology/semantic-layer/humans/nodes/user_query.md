# :UserQuery

Nodo de consulta de usuario. Creado por el LLM en runtime.

| Atributo | Tipo | Obligatorio | Descripción | Ejemplo |
|---|---|---|---|---|
| id_nodo | string | sí | Identificador único del nodo (UUID v4) | `a1b2-...` |
| user_id | string | no | Identificador del usuario. Default: "unknown" | `user-42` |
| user_prompt | string | sí | Prompt en lenguaje natural enviado por el usuario | `¿Qué dice la Ley 39/2015?` |
| bbdd_query | string[] | sí | Consultas Cypher generadas por el LLM a partir del prompt | `["MATCH (n:Norma)..."]` |
| answer | string | sí | Respuesta en lenguaje natural devuelta al usuario | `La ley establece...` |
