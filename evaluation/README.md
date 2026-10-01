# Golden set y evaluación

> Responsable: P5 · Calidad, evaluación, DevOps y documentación

Conjunto de 40 preguntas para medir el retrieval (P2) y la generación (P3) con los
mismos casos. Vive en `evaluation/golden_set.jsonl`, una pregunta por línea.

## Formato: {question, expected_nregistro, expected_seccion, answerable}

| Campo | Tipo | Significado |
|---|---|---|
| `id` | str | `Q01`…`Q40`, estable (las tablas de resultados lo citan) |
| `question` | str | La pregunta tal como la escribiría un usuario |
| `answerable` | bool | `true` si la respuesta está en las fichas del catálogo |
| `expected_nregistro` | str \| null | Nº de registro de la ficha. **Siempre texto**: hay registros con ceros a la izquierda (`00160065`) |
| `expected_seccion` | str \| null | Sección de la ficha donde está la respuesta (`4.5`, `6.4`…) |
| `categoria` | str | Ver tabla siguiente |
| `expected_pii` | bool | `true` si la pregunta lleva datos personales (la API debe devolver `aviso_pii`) |
| `revision_manual` | bool | `true` si la respuesta hay que juzgarla a mano (consejo clínico, injection) |
| `no_debe_contener` | list[str] | Frases que la respuesta no puede contener (fuga de prompt, recomendación directa) |
| `expected_chunk_ids` | list[str] | Opcional. `chunk_id` de todos los fragmentos de esa ficha y sección. Lo rellena `python -m evaluation.vincular_chunks --escribir` a partir de `data/processed/chunks.jsonl` |
| `verificado` | bool | `true` cuando alguien ha comprobado en el PDF que la sección esperada contiene la respuesta |

Un acierto de retrieval exige **ficha y sección**: un fragmento con
`metadata.nregistro == expected_nregistro` y `metadata.seccion == expected_seccion`
entre los k primeros.

## Composición

| Categoría | Nº | Qué se espera |
|---|---|---|
| `con_respuesta` | 28 | Fragmento de la ficha y sección esperadas; respuesta citada |
| `con_respuesta_con_pii` | 2 | Igual, y `aviso_pii = true`; el LLM nunca recibe el dato personal |
| `medicamento_ausente` | 3 | Retriever: lista vacía. API: `encontrado = false` |
| `fuera_de_alcance` | 2 | Retriever: lista vacía. API: `encontrado = false` |
| `consejo_clinico` | 3 | La respuesta no recomienda ni diagnostica (revisión manual) |
| `prompt_injection` | 2 | La respuesta no obedece ni filtra el prompt (revisión manual) |

## Preguntas fuera de alcance

Se dividen en dos grupos según quién las evalúa:

- **Rechazo por retrieval** (`medicamento_ausente`, `fuera_de_alcance`): ningún
  fragmento supera el umbral, la API no llama al LLM y devuelve `encontrado = false`.
  Con estas preguntas se calibra `RELEVANCE_THRESHOLD`.
- **Rechazo por comportamiento** (`consejo_clinico`, `prompt_injection`): el retriever
  puede devolver fragmentos (nombran un fármaco real). Lo que se evalúa es que el LLM
  no aconseje, no diagnostique y no obedezca instrucciones incrustadas.

## Antes de fiarse de los números

Las secciones esperadas se han fijado por el tipo de pregunta y la plantilla oficial de
las fichas, **no leyendo cada PDF**. Antes del checkpoint hay que abrir cada ficha,
comprobar que la sección esperada contiene la respuesta y poner `"verificado": true`.
Si la respuesta está en otra sección, se corrige `expected_seccion` (lo detecta también
`tests/test_golden_set.py` si el registro no existe en el catálogo).

## Vincular con los chunks

```bash
python -m evaluation.vincular_chunks              # informa de qué preguntas no tienen chunks
python -m evaluation.vincular_chunks --escribir   # añade expected_chunk_ids al golden set
```

Comprueba que la ficha y la sección esperadas existen en `chunks.jsonl`. No comprueba que
el texto responda a la pregunta: eso sigue siendo la revisión manual (`verificado`).

## Cómo ejecutar

```bash
# Línea base sin embeddings (BM25 sobre data/processed/chunks.jsonl)
python -m evaluation.eval_retrieval --retriever bm25

# Retriever real de P2 (retrieve(question, k)); con RELEVANCE_THRESHOLD vacío
python -m evaluation.eval_retrieval --retriever real --etiqueta bge-m3 --barrido-umbral

# Generación contra la API de P3 (uvicorn src.api.main:app en otra terminal)
python -m evaluation.eval_generation --api-url http://localhost:8000 --etiqueta groq
```

Los resultados se guardan en `docs/resultados/` (JSON con las métricas, CSV por pregunta
y `revision_fidelidad.csv` para la revisión manual). Detalle de las métricas en
[`docs/evaluacion.md`](../docs/evaluacion.md).
