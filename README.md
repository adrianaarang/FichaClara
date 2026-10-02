# FichaClara · Asistente RAG sobre fichas técnicas de medicamentos (AEMPS/CIMA)

> Responsable: P5 · Calidad, evaluación, DevOps y documentación

## Caso de uso y valor

FichaClara responde en lenguaje natural preguntas sobre medicamentos usando **solo** las fichas técnicas oficiales de la AEMPS (CIMA) y cita en cada respuesta el medicamento, la sección (p. ej. 4.5 Interacciones), la página y un enlace a CIMA. Si la respuesta no está en las fichas indexadas, lo dice en lugar de inventarla.

**Problema.** Una ficha técnica tiene entre 10 y 40 páginas y los datos clave están repartidos por secciones. Preguntas como «¿se puede triturar?» o «¿interacciona con el acenocumarol?» se resuelven hoy buscando a mano en el PDF o preguntando a farmacia. La búsqueda de CIMA es por nombre, y un chatbot genérico puede alucinar sin decir de dónde saca el dato.

**Usuarios.** Enfermería de residencias y hospitalización, farmacia hospitalaria o de residencia, estudiantes y personal en formación, y proveedores de software sanitario (módulo reutilizable vía API).

**Fuera de alcance.** Recomendaciones clínicas individualizadas, diagnóstico o prescripción, tratar datos de pacientes reales y sustituir la consulta al farmacéutico o al médico. No es un sistema de apoyo a la decisión clínica: es un buscador inteligente sobre documentación oficial que siempre enseña la fuente para que el profesional la verifique.

## Arquitectura

Dos flujos que comparten la base vectorial (ChromaDB): **ingesta** (CIMA o documento subido → limpieza → chunking por sección → embeddings locales → índice) y **consulta** (pregunta → filtro PII → retriever con umbral → cadena RAG con prompt de grounding → LLM → validación de citas → respuesta con fuentes). Si ningún fragmento supera el umbral, la API responde `encontrado = false` sin llamar al LLM.

Diagrama, flujos paso a paso y contratos entre módulos en [`docs/arquitectura.md`](docs/arquitectura.md). Decisiones técnicas en [`docs/decisiones_tecnicas.md`](docs/decisiones_tecnicas.md).

## Instalación

Requisitos: Python 3.11+ (probado en 3.14).

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1          # en Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env              # y rellena las claves que necesites (LLM_PROVIDER, GROQ_API_KEY...)
```

## Variables de entorno (.env)

Se copian de `.env.example` a `.env` (nunca se sube al repositorio).

| Variable | Para qué sirve | Valor de ejemplo |
|---|---|---|
| `LLM_PROVIDER` | Proveedor del LLM | `groq` o `ollama` |
| `GROQ_API_KEY`, `GROQ_MODEL` | Clave y modelo de Groq (API comercial) | — |
| `OLLAMA_BASE_URL`, `OLLAMA_MODEL` | Servidor y modelo de Ollama (local) | `http://localhost:11434` |
| `EMBEDDING_MODEL` | Modelo de embeddings (local) | `BAAI/bge-m3` |
| `CHROMA_DIR`, `CHROMA_COLLECTION` | Carpeta y colección de ChromaDB | `data/chroma`, `fichas_tecnicas` |
| `RETRIEVER_K` | Nº de fragmentos que se recuperan | `5` |
| `RELEVANCE_THRESHOLD` | Puntuación mínima para considerar relevante un fragmento (`.env.example` lo deja vacío) | se calibra con `eval_retrieval --barrido-umbral` |
| `API_URL` | URL de la API para el frontend | `http://localhost:8000` |
| `PII_FILTER_ENABLED` | Activa el filtro de datos personales | `true` (por defecto) |

## Cómo ejecutar (ingesta → indexado → API → frontend)

De momento, la parte de ingesta funciona de punta a punta:

```powershell
# 1. Descargar las fichas técnicas del catálogo desde CIMA a data/raw/
python -m scripts.download_fichas

# 2. Procesarlas: cargar → limpiar → trocear → guardar en data/processed/chunks.jsonl
python -m src.ingestion.pipeline

# 3. Validar que el chunker detecta bien las secciones oficiales de CIMA
python -m src.ingestion.validacion
```

El resto del pipeline (indexado en Chroma, API, frontend) está en desarrollo — se documentará aquí a medida que cada módulo esté listo.



## Estrategia de chunking (resumen + enlace a docs/chunking.md)

Cada sección numerada de la ficha técnica (4.1 Indicaciones, 4.2 Posología, 4.5 Interacciones...) se trocea como una unidad propia, en vez de partir el documento por tamaño fijo: así cada fragmento responde a un único tipo de pregunta y nunca mezcla, por ejemplo, interacciones con embarazo. Las secciones largas (>1.500 caracteres) se subdividen en trozos de 1.000 caracteres con un 15 % de solape, siempre dentro de la misma sección. Cada chunk lleva una cabecera de contexto (`[Medicamento · 4.5 Interacciones]`) y metadatos completos (medicamento, sección, página, fecha, enlace a CIMA).

Se validó contra la segmentación oficial de CIMA en las 235 fichas del catálogo: 100 % de cobertura, 99,8 % de precisión. Un experimento comparando este troceo con uno de tamaño fijo (500/1.000 caracteres) confirma la decisión: el troceo por sección no mezcla nunca dos secciones distintas (0,0 %) frente al 11,5–21,3 % del troceo fijo.

Detalle completo, con las tablas de resultados: [`docs/chunking.md`](docs/chunking.md).

## Modelo de embeddings y base vectorial (resumen)

_TODO_

## Evaluación y resultados

El golden set (40 preguntas: 30 con respuesta y 10 sin respuesta o fuera de alcance) está en `evaluation/golden_set.jsonl`. Las métricas de retrieval (hit rate@k, MRR, acierto de sección, rechazo correcto) y de generación (citas válidas, cita correcta, aviso PII, fidelidad) se reproducen con un comando cada una:

```
# Retrieval: línea base BM25 o retriever real de P2
python -m evaluation.eval_retrieval --retriever bm25
python -m evaluation.eval_retrieval --retriever real --etiqueta bge-m3 --barrido-umbral

# Generación: contra la API en marcha
python -m evaluation.eval_generation --api-url http://localhost:8000
```

Los resultados se guardan en `docs/resultados/`. Definición de las métricas y tablas de resultados en [`docs/evaluacion.md`](docs/evaluacion.md); formato del golden set en [`evaluation/README.md`](evaluation/README.md).

_Resultados pendientes del checkpoint de retrieval._

## Limitaciones y aviso sanitario

> **Aviso sanitario.** FichaClara es un buscador sobre documentación oficial, no un sistema de apoyo a la decisión clínica. No sustituye la consulta al farmacéutico ni al médico. Verifica siempre la información en la fuente citada.

- Solo conoce las fichas del catálogo; lo que no esté ahí responde «no consta en las fichas consultadas».
- Las fichas cambian: el índice refleja el momento de la descarga. La fecha de revisión de cada ficha se muestra en la fuente.
- Las tablas de la sección 4.8 (reacciones adversas) pueden extraerse del PDF de forma desordenada.
- El filtro de datos personales funciona por reglas y no es un anonimizador certificado: no escribas datos de pacientes reales. Para un despliegue real en un centro, usa el modo local (Ollama).
- El catálogo tiene fichas que no coinciden exactamente con el principio activo buscado (`docs/resultados/catalogo_discrepancias.csv`).

Detalle en [`docs/etica_y_privacidad.md`](docs/etica_y_privacidad.md).

## Equipo y reparto

| Rol | Persona | Módulo |
|---|---|---|
| P1 | Adriana | Ingesta y chunking (`src/ingestion/`, `data/catalogo_medicamentos.csv`) |
| P2 | David | Embeddings, base vectorial y retrieval (`src/indexing/`, `src/retrieval/`) |
| P3 | Josema | Orquestación LLM y API (`src/generation/`, `src/api/`, `src/common/`) |
| P4 | Anas | Frontend y experiencia de usuario (`frontend/`) |
| P5 | Yohanna | Calidad, evaluación, gobernanza y documentación (`evaluation/`, `src/guardrails/`, `.github/`, `docs/`) |

Cada carpeta pertenece a una sola persona, con sus propios tests y su ADR. Solo `src/common/`, `requirements.txt` y el README se tocan entre varios, siempre por PR.

## Flujo de trabajo Git

- **Ramas**: `main` (entregable, protegida) ← `develop` (integración, protegida) ← `feature/p1-chunker`, `feature/p3-api-query`, `fix/p2-umbral`…
- **Issues**: cada tarea es una issue con etiqueta de rol (`p1`–`p5`) y criterio de aceptación. Las PR la cierran con `Closes #n`.
- **Pull requests**: siempre a `develop`, pequeñas (idealmente menos de 300 líneas), con CI en verde (`ruff` + `pytest`) y una aprobación.
- **Revisión cruzada**: P1 → revisa P2 → revisa P3 → revisa P4 → revisa P5 → revisa P1.
- **Commits convencionales**: `feat(ingestion): detectar secciones 4.x`, `fix(retrieval): umbral en preguntas vacías`, `docs(chunking): tabla del experimento`, `test(api): …`.
- **Merge a `main`**: al final de cada sprint (`develop` → `main`), con etiqueta `v0.1` y `v1.0`.
- **Nunca en el repositorio**: `.env`, claves de API, `data/raw`, `data/chroma`.
