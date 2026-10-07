# Evaluación

> Responsable: P5 · Calidad, evaluación, DevOps y documentación

La evaluación mide dos cosas por separado, en este orden: primero si **se recuperan los
fragmentos correctos** (retrieval, checkpoint del día 5) y después si **la respuesta es
fiable** (generación). Ambas usan el mismo golden set.

## Golden set

40 preguntas en `evaluation/golden_set.jsonl` (formato y composición en
[`evaluation/README.md`](../evaluation/README.md)):

- 30 con respuesta en las fichas (28 normales y 2 con datos personales), repartidas en
  13 secciones de la plantilla (4.1–4.9, 5.2, 6.1, 6.3, 6.4) y 30 fichas distintas (una por pregunta).
- 10 sin respuesta: 3 medicamentos fuera del catálogo, 2 fuera de tema, 3 de consejo
  clínico o diagnóstico y 2 intentos de prompt injection.

Cada pregunta con respuesta lleva un par esperado `(nregistro, sección)`. El campo
`verificado` indica si una persona ha comprobado en el PDF que esa sección contiene la
respuesta.

## Métricas de retrieval (checkpoint)

Se calculan con `python -m evaluation.eval_retrieval` sobre las 30 preguntas con
respuesta, salvo las de rechazo.

| Métrica | Definición |
|---|---|
| **hit rate@k** | % de preguntas con al menos un fragmento de la ficha **y** la sección esperadas entre los k primeros (k = 1, 3, 5). Objetivo orientativo: ≥ 0,85 en @5 |
| **acierto de ficha@k** | Igual, pero solo exige la ficha. Si es alto y el hit rate es bajo, el problema es la sección |
| **MRR** | Media de 1/posición del primer acierto (0 si no aparece en los k). Mide si el acierto sale arriba |
| **acierto de sección@1** | % de preguntas cuyo primer fragmento es de la sección esperada, sea de la ficha que sea |
| **rechazo correcto** | % de preguntas `medicamento_ausente` y `fuera_de_alcance` para las que el retriever devuelve lista vacía |
| **falsos rechazos** | % de preguntas con respuesta para las que devuelve lista vacía |

Las preguntas pasan antes por el filtro PII, igual que en la API. Con `--barrido-umbral`
se recalculan hit rate, rechazo correcto y falsos rechazos para distintos umbrales de
similitud. Esta herramienta se utilizó para comprobar si existía un corte global capaz de
separar de forma fiable las preguntas respondibles de las que debían rechazarse.

La evaluación mostró que ambas distribuciones se solapan, por lo que la configuración final
mantiene `RELEVANCE_THRESHOLD=None` y el rechazo se apoya en el catálogo y en las reglas
del flujo RAG.

### Cómo comparar modelos de embeddings (P2)

Cada modelo necesita su propio índice (dimensiones y espacio vectorial distintos):

```bash
EMBEDDING_MODEL=BAAI/bge-m3 CHROMA_DIR=data/chroma_bge \
  python -m scripts.build_index --persist-directory data/chroma_bge
EMBEDDING_MODEL=BAAI/bge-m3 CHROMA_DIR=data/chroma_bge \
  python -m evaluation.eval_retrieval --retriever real --etiqueta bge-m3 --barrido-umbral

EMBEDDING_MODEL=intfloat/multilingual-e5-base CHROMA_DIR=data/chroma_e5 \
  python -m scripts.build_index --persist-directory data/chroma_e5
EMBEDDING_MODEL=intfloat/multilingual-e5-base CHROMA_DIR=data/chroma_e5 \
  python -m evaluation.eval_retrieval --retriever real --etiqueta e5-base --barrido-umbral
```

Dos precauciones para que la comparación sea justa: `multilingual-e5` espera los prefijos
`query: ` y `passage: ` (sin ellos rinde peor), y el barrido de umbral debe hacerse con
`relevance_threshold=None` (el valor por defecto de `retrieve()`), porque cada modelo tiene su
propia escala de puntuaciones.

Comparativas utilizadas para la decisión de retrieval:

1. Línea base léxica con BM25.
2. `multilingual-e5-base`.
3. `BAAI/bge-m3`.
4. Búsqueda híbrida `bge-m3 + BM25` mediante Reciprocal Rank Fusion.

La estrategia de chunking se evaluó además de forma independiente frente a troceos fijos
de 500 y 1.000 caracteres. Los resultados de ese experimento están documentados en
[`chunking.md`](chunking.md).

## Métricas de generación

Se calculan con `python -m evaluation.eval_generation` contra `POST /query`.

| Métrica | Definición | Objetivo |
|---|---|---|
| **rechazo correcto** | `encontrado = false` en las preguntas de rechazo por retrieval | 100 % |
| **falsos rechazos** | `encontrado = false` en preguntas con respuesta | lo más bajo posible |
| **citas válidas** | Todo `[n]` del texto corresponde a una fuente de la respuesta | 100 % (criterio de P3) |
| **cita correcta** | Una fuente citada es la ficha y sección esperadas | ≥ 0,85 |
| **aviso PII** | `aviso_pii = true` cuando la pregunta lleva datos personales, y no salta sin ellos | 100 % / 0 % |
| **sin fuga** | La respuesta no contiene las frases prohibidas de la pregunta | 100 % |
| **fidelidad** | Lo afirmado está en los fragmentos citados | revisión manual |

La fidelidad no se decide con reglas. El script genera `docs/resultados/revision_fidelidad.csv`
con la pregunta, la respuesta y los fragmentos; dos personas del equipo rellenan la columna
`fiel` (sí / no / parcial) y se anota el % de «sí». Si sobra tiempo se puede añadir un LLM
como juez, pero solo como segunda opinión: la decisión final es humana en un ámbito
sanitario.

## Preguntas fuera de alcance

- **Sin respuesta en el catálogo**: se espera lista vacía y `encontrado = false` sin llamar
  al LLM.
- **Consejo clínico o diagnóstico**: se espera una respuesta que no recomiende ni
  diagnostique. Se revisan a mano.
- **Prompt injection**: se espera que la respuesta no revele el prompt ni abandone el
  grounding. Se revisan a mano y con frases prohibidas.

## Resultados

### Retrieval

La comparación se realizó sobre el mismo corpus de **18.143 chunks** y las mismas
30 preguntas respondibles del golden set.

| Configuración | hit@1 | hit@3 | hit@5 | MRR |
|---|---:|---:|---:|---:|
| BM25 | 36,7 % | 50,0 % | 60,0 % | 0,4456 |
| multilingual-E5-base | 60,0 % | 76,7 % | 80,0 % | 0,6844 |
| BGE-M3 + BM25 | 56,7 % | 70,0 % | 80,0 % | 0,6528 |
| **BGE-M3** | **60,0 %** | **80,0 %** | **86,7 %** | **0,7111** |

`BAAI/bge-m3` obtuvo el mejor resultado global y se adoptó como modelo principal.

Con BGE-M3, la **ficha correcta apareció dentro del Top 5 en el 100 % de los casos
respondibles evaluados**. La diferencia respecto al hit@5 completo, 86,7 %, indica que
los errores restantes se concentran principalmente en el ranking de la sección correcta
dentro de una ficha ya identificada.

También se evaluó un guard basado en el catálogo para las consultas sin un medicamento
conocido. Con esta configuración:

- hit@5: **86,7 %**;
- MRR: **0,7111**;
- ficha correcta@5: **100 %**;
- rechazo correcto: **100 %**;
- falsos rechazos: **0 %**.

### Umbral de similitud

No se adopta un umbral global de relevancia.

El mayor score observado entre las preguntas que debían rechazarse fue **0,7081**,
mientras que una pregunta respondible llegó a obtener **0,5788**.

Por tanto, un único corte no separa ambos grupos: un umbral suficientemente alto para
rechazar determinados casos descartaría también preguntas válidas.

La configuración final mantiene:

```text
RELEVANCE_THRESHOLD=None
```

y combina catálogo, detección del medicamento, recuperación Top 5 y las reglas
posteriores del flujo RAG.

> **Nota sobre las métricas:** los resultados de retrieval se consideran preliminares
> hasta completar la verificación manual de las preguntas respondibles del golden set
> contra los PDF originales.

### Generación

La evaluación de generación está implementada en `evaluation/eval_generation.py` y
permite comprobar automáticamente rechazo, citas, PII y ausencia de determinadas fugas
contra la API real.

La **fidelidad semántica** de la respuesta no se da por válida mediante una regla
automática. El proceso genera `docs/resultados/revision_fidelidad.csv` para que una
persona revise la respuesta frente a los fragmentos citados.

Por este motivo no se publica un porcentaje agregado de fidelidad sin esa revisión humana.
En un dominio sanitario, la evaluación automática se utiliza como apoyo y no sustituye la
comprobación manual de la evidencia.

### Limitaciones del propio golden set

- 40 preguntas dan una idea, no una estimación precisa: con 30 preguntas, un punto de
  hit rate son 3 puntos porcentuales.
- Las preguntas las ha escrito el equipo. No sustituyen a las que haría personal de
  enfermería real.
- El catálogo tiene una ficha por principio activo, así que no se evalúa la ambigüedad
  entre marcas ni entre presentaciones.
