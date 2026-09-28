# Estrategia de chunking

Responsable: Adriana (P1) · Ingesta y chunking

## 1. La unidad de chunk: la sección de la ficha técnica

Todas las fichas técnicas autorizadas en España (y las EMA que usamos como catálogo
complementario) siguen la misma plantilla oficial de secciones numeradas: 1–3 identifican
el medicamento, 4.1–4.9 son los datos clínicos (indicaciones, posología, contraindicaciones,
interacciones, reacciones adversas...), 5 las propiedades farmacológicas, 6 los datos
farmacéuticos, y 7–10 metadatos de vigencia (titular, autorización, fechas).

Cada sección responde a un tipo de pregunta distinto: "¿para qué está indicado?" (4.1),
"¿se puede triturar?" (4.2), "¿interacciona con el omeprazol?" (4.5). Por eso la decisión de
diseño es trocear por sección en vez de por tamaño fijo: un fragmento de tamaño fijo puede
empezar a mitad de "Interacciones" y terminar a mitad de "Embarazo y lactancia", mezclando
dos respuestas distintas en un mismo chunk y diluyendo el embedding.

Reglas:

- Solo se aceptan como títulos los números de la plantilla oficial (`PLANTILLA` en
  `chunker.py`), en orden y con un título que encaje semánticamente con esa sección. Así no
  se confunde "(ver sección 4.3)" ni una lista "1. Poner el parche..." con un título real.
- Si una ficha reconoce menos de 8 secciones de la plantilla, se asume que el PDF tiene un
  formato raro y se usa el troceo genérico (fallback) en vez de forzar una segmentación
  incorrecta.

## 2. Secciones largas: subtroceo dentro de la sección

Algunas secciones (4.8 Reacciones adversas, 5.1 Farmacodinamia) pueden ocupar varias
páginas. Si una sección supera los **1.500 caracteres** (`MAX_SECCION`), se subdivide con
`RecursiveCharacterTextSplitter` en trozos de **1.000 caracteres** (`TAM_CHUNK`) con un
**solape de 150 caracteres** (`SOLAPE`, ~15 %) — pero el subtroceo nunca cruza el límite de
la sección: un subtrozo de 4.8 nunca contiene también texto de 4.9. El solape solo sirve para
no cortar una frase o una fila de tabla a mitad.

## 3. Cabecera contextual

Cada chunk empieza con una cabecera del tipo `[Lopresor 100 mg · 4.5 Interacción con otros
medicamentos]`. Un subtrozo suelto de la sección 4.8 no dice de qué fármaco habla ni de qué
sección viene; la cabecera lo pone explícito y mejora el retrieval porque ese contexto entra
en el embedding del propio fragmento, no solo en sus metadatos.

## 4. Metadatos

Cada chunk lleva: `nregistro`, `nombre`, `principios_activos`, `atc`, `seccion`,
`titulo_seccion`, `pagina_inicio`/`pagina_fin`, `fecha_revision`, `url_fuente` (enlace directo
a esa sección en CIMA) y `parte`/`total_partes` si la sección se subdividió. Esto da
trazabilidad completa (medicamento, sección, página, enlace) y permite filtrar la búsqueda
por medicamento.

## 5. Documentos que no son fichas técnicas

Una guía subida por el usuario no tiene secciones numeradas de la AEMPS. Para esos casos hay
un troceo recursivo genérico que respeta los encabezados Markdown si los hay, con el mismo
tamaño y solape que el subtroceo de secciones largas.

## 6. Validación de la detección de secciones

Antes de comparar estrategias de chunking hay que confirmar que el chunker detecta bien las
secciones. Se validó contra la segmentación oficial de CIMA (`docSegmentado/secciones`) en
las 235 fichas del catálogo (`src/ingestion/validacion.py`):

| Métrica | Resultado |
|---|---|
| Cobertura (recall) | 100 % |
| Precisión | 99,8 % |
| Cobertura en secciones clave (4.1–4.5, 4.8) | 99,9 % |
| Fichas idénticas a CIMA | 228 / 235 |

Las 7 fichas con diferencias solo tienen secciones "de más" respecto a CIMA (existen de
verdad en el PDF, pero faltan en la segmentación oficial de esas fichas concretas) — no son
errores de nuestro chunker. Informe completo en `docs/resultados/validacion_secciones.csv`.

## 7. Experimento: troceo fijo frente a troceo por sección

Para justificar la decisión con datos y no solo con el argumento teórico, se comparó nuestro
troceo por sección con un troceo "ingenuo" por tamaño fijo (500 y 1.000 caracteres, mismo
criterio de solape del ~15 %), sobre el texto ya limpio de las mismas fichas
(`src/ingestion/experimento_chunking.py`).

Métricas:

- **% de chunks que mezclan secciones**: de los chunks generados, cuántos contienen texto de
  más de una sección numerada distinta (p. ej. 4.5 y 4.6 en el mismo fragmento).
- **% de secciones clave enteras en un único chunk**: de las secciones 4.1, 4.2, 4.3, 4.4,
  4.5 y 4.8, cuántas quedan completas en un solo fragmento (sin partir su contenido entre
  varios chunks, lo que puede hacer que el fragmento recuperado se quede a medias).

> La comparación completa por *hit rate@k* con el golden set de evaluación (P5) queda
> pendiente de que existan el retriever (P2) y el golden set
> (`evaluation/golden_set.jsonl`, todavía vacío en el momento de escribir esto). Estas dos
> métricas no dependen de ningún otro módulo y ya muestran por qué el troceo por sección es
> mejor para este caso de uso; cuando el retriever esté listo, este script se puede ampliar
> con hit rate@k por estrategia y añadir esa fila a la tabla.

Resultado sobre las 235 fichas del catálogo (`python -m src.ingestion.experimento_chunking`):

| Estrategia | Nº chunks | Tamaño medio | % chunks con mezcla de secciones | % secciones clave enteras |
|---|---|---|---|---|
| Fijo 500 | 33.313 | 329 | 11,5 % | 10,6 % |
| Fijo 1.000 | 15.356 | 724 | 21,3 % | 17,4 % |
| **Por sección** | 17.895 | 711 | **0,0 %** | **40,0 %** |

Lectura:

- **Mezcla de secciones (el criterio decisivo)**: el troceo por sección no mezcla nunca dos
  secciones numeradas distintas en el mismo fragmento (0,0 %), por construcción. El troceo
  fijo sí lo hace, y cuanto más grande el tamaño del chunk, más mezcla: 11,5 % con 500
  caracteres, 21,3 % con 1.000. Ese porcentaje de chunks del troceo fijo responde, si se
  recupera, con contenido de dos secciones a la vez — exactamente lo que la unidad de chunk
  por sección evita.
- **Secciones clave enteras en un único chunk**: el troceo por sección deja el 40,0 % de las
  secciones clave (4.1–4.5, 4.8) enteras en un solo fragmento, frente al 10,6–17,4 % del
  troceo fijo. El 60 % restante de nuestras secciones clave no cabe en los 1.500 caracteres
  de `MAX_SECCION` (4.8 y 4.4 son las más largas habitualmente) y se subdivide en varias
  partes — pero, a diferencia del troceo fijo, **nunca mezclado con otra sección**: cada
  parte de un 4.8 largo sigue siendo solo 4.8, con su propia cabecera de contexto y solape,
  así que el fragmento recuperado nunca es ambiguo sobre de qué sección viene, aunque no
  contenga la sección completa.

**Conclusión**: se mantiene el troceo por sección como estrategia principal. La métrica que
más pesa para este caso de uso — no mezclar dos secciones que responden a preguntas
distintas — pasa de un 11,5–21,3 % de "contaminación" en el troceo fijo a un 0,0 % con el
troceo por sección. El coste es que las secciones más largas quedan repartidas en varias
partes en vez de en un único chunk, y se mitiga con el solape del 15 % y con que la cabecera
de contexto y el metadato `seccion`/`parte`/`total_partes` identifican cada fragmento sin
ambigüedad. El troceo fijo se descarta como estrategia principal (queda documentado aquí
como comparación, no como fallback — el fallback real es el troceo genérico por encabezados
Markdown para documentos sin plantilla, sección 5).

## Informe completo

`docs/resultados/experimento_chunking.csv` (por estrategia) y
`docs/resultados/validacion_secciones.csv` (ficha a ficha, frente a CIMA).
