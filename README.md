# FichaClara · Asistente RAG sobre fichas técnicas de medicamentos (AEMPS/CIMA)

> Responsable: P5 · Calidad, evaluación, DevOps y documentación

## Caso de uso y valor

_TODO_

## Arquitectura

_TODO_

## Instalación

Requisitos: Python 3.11+ (probado en 3.14).

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1          # en Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env              # y rellena las claves que necesites (LLM_PROVIDER, GROQ_API_KEY...)
```

## Variables de entorno (.env)

_TODO_

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

_TODO_

## Limitaciones y aviso sanitario

_TODO_

## Equipo y reparto

_TODO_

## Flujo de trabajo Git

_TODO_
