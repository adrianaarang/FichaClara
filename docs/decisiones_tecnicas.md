# Decisiones técnicas (ADR)

> Responsable: P5 · Calidad, evaluación, DevOps y documentación

## ADR-01 Modelo de embeddings (P2)

_TODO_

## ADR-02 Base vectorial (P2)

_TODO_

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
