# :UserQuery

Nodo de consulta de usuario. Creado por el LLM en runtime.

| Atributo | Tipo | Obligatorio | Descripción | Ejemplo |
|---|---|---|---|---|
| id_nodo | string | sí | Identificador único del nodo (UUID v4) | `a1b2c3d4-e5f6-7890-abcd-ef1234567890` |
| user_id | string | no | Identificador del usuario | `unknown` |
| user_prompt | string | sí | Prompt en lenguaje natural enviado por el usuario | `¿Cuántos reales decretos ha emitido el Ministerio de Hacienda?` |
| bbdd_query | string[] | sí | Consultas Cypher generadas por el LLM a partir del prompt | `["MATCH (n:Norma {rango: 'Real Decreto', departamento: 'Ministerio de Hacienda'}) RETURN count(n) AS total"]` |
| answer | string | sí | Respuesta en lenguaje natural devuelta al usuario | `El Ministerio de Hacienda ha emitido 312 reales decretos en el grafo.` |
| ts | string | sí | Timestamp ISO-8601 de creación del nodo (datetime() de Neo4j) | `2025-06-01T12:00:00Z` |
