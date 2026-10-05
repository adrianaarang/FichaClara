# Decisiones técnicas (ADR)

> Responsable: P5 · Calidad, evaluación, DevOps y documentación

## ADR-01 Modelo de embeddings (P2)

**Contexto**: el retriever necesita representar en el mismo espacio semántico preguntas en español y fragmentos de fichas técnicas de medicamentos. El objetivo orientativo del proyecto es alcanzar un `hit rate@5 >= 0,85` sobre el golden set de retrieval.

**Decisión**: usar `BAAI/bge-m3` como modelo de embeddings, con normalización de vectores y similitud coseno. El modelo se ejecuta en CPU en el entorno actual.

**Alternativa evaluada**: `intfloat/multilingual-e5-base`, usando los prefijos recomendados `query: ` para preguntas y `passage: ` para documentos. Se construyó un índice independiente porque ambos modelos generan espacios vectoriales distintos.

**Experimento**: sobre el mismo corpus de 18.143 chunks y el mismo golden set, sin aplicar un umbral de relevancia:

| Modelo | hit@1 | hit@3 | hit@5 | MRR | acierto ficha@5 |
|---|---:|---:|---:|---:|---:|
| `BAAI/bge-m3` | 60,0 % | 80,0 % | **86,7 %** | **0,7111** | 100,0 % |
| `intfloat/multilingual-e5-base` | 60,0 % | 76,7 % | 80,0 % | 0,6844 | 100,0 % |

Como referencias adicionales, BM25 obtuvo `hit@5 = 60,0 %` y `MRR = 0,4456`. También se probó una combinación `bge-m3 + BM25` mediante Reciprocal Rank Fusion, que obtuvo `hit@5 = 80,0 %` y `MRR = 0,6528`, por lo que no mejoró al retriever vectorial puro.

**Decisión sobre el umbral**: no fijar por ahora un `RELEVANCE_THRESHOLD` global y mantenerlo en `None`. Las distribuciones de score de preguntas respondibles y preguntas fuera del corpus se solapan: el mayor score observado en una pregunta de rechazo fue `0,7081`, mientras que una pregunta respondible llegó a `0,5788`. Por tanto, un único corte por similitud produciría falsos rechazos antes de separar de forma fiable las consultas fuera de alcance.

Para las consultas sin un medicamento conocido se usa en su lugar el catálogo: con este guard el `hit@5` se mantiene en 86,7 %, el rechazo correcto pasa de 0 % a 100 % y los falsos rechazos permanecen en 0 %. Las consultas que mencionan varios medicamentos conocidos mantienen búsqueda global para permitir preguntas de interacción.

**Consecuencias**:
- Positivas: `bge-m3` es el único modelo evaluado que supera el objetivo orientativo de `hit rate@5 >= 0,85`; identifica la ficha correcta en el 100 % de las preguntas respondibles del golden set.
- Negativas: el ranking dentro de una ficha todavía falla en algunas secciones, especialmente en preguntas de indicaciones, contraindicaciones y posología. Las preguntas Q04, Q20, Q24 y Q28 no recuperan la sección esperada en el top 5.
- El índice debe reconstruirse si cambia el modelo de embeddings.
- Estos resultados son preliminares mientras las preguntas respondibles del golden set sigan pendientes de verificación manual contra los PDF.

## ADR-02 Base vectorial (P2)

**Contexto**: el índice debe ser persistente, funcionar localmente, soportar filtrado por metadatos de la ficha técnica y permitir reconstrucción y actualización sin duplicar chunks.

**Decisión**: usar Chroma como base vectorial persistente, integrada mediante `langchain-chroma`, con distancia coseno.

Cada chunk se almacena usando `chunk_id` como identificador estable. La capa de indexación soporta:
- alta o actualización de chunks por `chunk_id`;
- borrado de todos los chunks asociados a un documento;
- listado de documentos indexados;
- filtros por metadatos, especialmente `nregistro`.

El retriever aplica el filtro por `nregistro` cuando detecta exactamente un medicamento conocido. Si detecta varios medicamentos conocidos, mantiene búsqueda global para permitir consultas de interacción. Si no detecta ningún medicamento del catálogo, devuelve una lista vacía sin consultar Chroma.

**Justificación**: Chroma cubre los requisitos definidos para P2 sin introducir infraestructura externa: persistencia local, almacenamiento de metadatos, filtrado y compatibilidad directa con LangChain. En este proyecto no se realizó un benchmark comparativo entre distintos motores vectoriales, por lo que la decisión se basa en adecuación a los requisitos de la arquitectura y no en una afirmación de superioridad frente a otras bases vectoriales.

**Consecuencias**:
- Positivas: índice local y reproducible, filtrado por ficha técnica y actualizaciones idempotentes mediante identificadores estables.
- Positivas: permite mantener índices independientes para modelos de embeddings distintos.
- Negativas: el índice está ligado al modelo con el que fue construido; no puede consultarse correctamente con embeddings de otro modelo.
- Negativas: cambiar de modelo requiere crear o reconstruir un índice compatible.

## ADR-03 Orquestador y LLM (P3)

_TODO_

## ADR-04 Frontend (P4)

_TODO_

## ADR-05 Chunking (Adriana)

**Contexto**: las fichas técnicas de la AEMPS siguen una plantilla oficial de secciones numeradas (4.1 Indicaciones, 4.2 Posología, 4.5 Interacciones...), y cada sección responde a un tipo de pregunta distinto. Había que decidir la unidad de chunk para indexar en Chroma.

**Decisión**: trocear por sección numerada de la plantilla oficial, no por tamaño fijo. Las secciones que superan 1.500 caracteres se subdividen en trozos de 1.000 con un 15 % de solape, siempre dentro de la misma sección (nunca mezclando 4.5 con 4.6). Cada chunk lleva una cabecera de contexto (`[Medicamento · 4.5 Interacciones]`) y metadatos completos (medicamento, sección, página, fecha, enlace a CIMA).

**Alternativas consideradas**:
- *Troceo fijo (500 o 1.000 caracteres), sin respetar secciones*: más simple de implementar, pero mezcla contenido de secciones distintas en un mismo fragmento.
- *Una sección por chunk sin subtroceo, aunque sea muy larga*: evita el solape, pero produce embeddings poco específicos en secciones largas (4.8, 5.1) al diluir el contenido relevante entre mucho texto.

**Experimento**: se comparó el troceo por sección con troceo fijo de 500 y 1.000 caracteres sobre las 235 fichas del catálogo (`src/ingestion/experimento_chunking.py`). El troceo por sección no mezcla nunca dos secciones numeradas (0,0 %), frente al 11,5–21,3 % del troceo fijo. Detalle completo en `docs/chunking.md`.

**Consecuencias**:
- Positivas: cada chunk recuperado es semánticamente puro (una sola sección) y trazable (metadatos + enlace a CIMA); validado contra la segmentación oficial de CIMA con 100 % de cobertura y 99,8 % de precisión en las 235 fichas.
- Negativas: las secciones más largas (4.8, 4.4) quedan repartidas en varias partes en un 60 % de los casos, en vez de un único chunk completo; se mitiga con el solape del 15 % y el metadato `parte`/`total_partes`.
- Documentos subidos sin plantilla (guías internas) usan un fallback genérico por encabezados Markdown, sin este análisis por sección.
