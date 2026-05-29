
// Briefing 1 — top 5 normas más modificadas (in-degree por verbos modificación)
MATCH (a:Norma)-[r]->(b:Norma)
WHERE type(r) IN ['MODIFICA','MODIFICA_DET','AÑADE','SUSTITUYE','SUPRIME']
RETURN b.id AS norma, count(r) AS n_mods
ORDER BY n_mods DESC LIMIT 5;

// Briefing 2 — top 5 normas que más modifican (out-degree)
MATCH (a:Norma)-[r]->(b:Norma)
WHERE type(r) IN ['MODIFICA','MODIFICA_DET','AÑADE','SUSTITUYE','SUPRIME']
RETURN a.id AS norma, count(r) AS n_mods_realizadas
ORDER BY n_mods_realizadas DESC LIMIT 5;

// Briefing 3a — % de normas vivas que citan al menos una derogada
MATCH (viva:Norma {vigente:true})-[:CITA|DEROGA|MODIFICA|DESARROLLA]->(otra:Norma)
WITH viva, sum(CASE WHEN otra.vigente=false THEN 1 ELSE 0 END) AS muertas_citadas
WITH count(viva) AS total_vivas,
     sum(CASE WHEN muertas_citadas > 0 THEN 1 ELSE 0 END) AS vivas_con_muertas
RETURN 100.0 * vivas_con_muertas / total_vivas AS porcentaje;

// Briefing 3b — top 5 normas muertas más citadas por normas vivas
MATCH (viva:Norma {vigente:true})-[r:CITA|DEROGA|MODIFICA|DESARROLLA]->(muerta:Norma {vigente:false})
RETURN muerta.id AS norma_muerta, count(viva) AS citas
ORDER BY citas DESC LIMIT 5;

// Briefing 4 — blast radius Ley 30/1992
MATCH (viva:Norma {vigente:true})-[r:CITA]->(:Norma {id:'BOE-A-1992-26318'})
RETURN viva.id, viva.titulo;