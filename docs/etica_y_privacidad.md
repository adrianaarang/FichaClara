# Ética, privacidad y gobernanza

> Responsable: P5 · Calidad, evaluación, DevOps y documentación

FichaClara **no es un sistema de apoyo a la decisión clínica**. Es un buscador inteligente
sobre documentación oficial que siempre enseña la fuente para que el profesional la
verifique. Este documento recoge qué datos se tratan, dónde puede haber fugas y qué
medidas se han tomado.

## Datos tratados

| Dato | Origen | Sensibilidad | Tratamiento |
|---|---|---|---|
| Fichas técnicas del catálogo | CIMA (AEMPS), documentos públicos | Ninguna | Se indexan en local, con embeddings locales |
| Preguntas del usuario | Escritas en el chat | Baja, salvo que incluyan datos de un paciente | Filtro PII antes de salir a una API comercial |
| Documentos subidos por el usuario | PDF, TXT, MD | Media: pueden ser guías internas o contener datos personales | Aviso en la subida; modo local recomendado |
| Respuestas del LLM | Generadas | Derivadas de las anteriores | No se guardan en el servidor |

La base de conocimiento no contiene datos personales. El riesgo está en lo que el usuario
escribe o sube.

Los datos de salud son una categoría especial en el RGPD (art. 9). Por eso el diseño parte
de minimizar: que el dato personal no llegue nunca al proveedor externo.

## API comercial vs modelo local

El proveedor se elige por variable de entorno (`LLM_PROVIDER=groq|ollama`), y se puede
cambiar en directo en la demo.

| Aspecto | Groq (API comercial) | Ollama (local) |
|---|---|---|
| Qué recibe el proveedor | La pregunta (ya enmascarada) y los fragmentos recuperados | Nada sale del equipo |
| Velocidad y calidad | Alta | Depende del hardware y del modelo |
| Coste | Nivel gratuito con límites | Sin coste de API |
| Cuándo | Preguntas genéricas, demo, desarrollo | Despliegue real en un centro sanitario, documentos internos |

Los embeddings (`bge-m3`) se calculan siempre en local, así que ni las fichas ni los
documentos subidos salen del equipo al indexar.

**Recomendación**: en un despliegue real en un centro, usar Ollama. Groq es aceptable
para las preguntas genéricas porque, con el filtro PII activo, no recibe datos de
pacientes.

## Riesgos de fuga de información (data leakage)

| Riesgo | Medida | Límite |
|---|---|---|
| El usuario escribe datos de un paciente en la pregunta | `check_pii` detecta DNI/NIE (comprueba la letra de control; si no cuadra lo enmascara igualmente y lo marca como `dni_posible`/`nie_posible`), teléfono, email, nº de historia clínica, tarjeta sanitaria, fecha de nacimiento y nombres, y los sustituye por `[DATO]` antes de llamar al LLM. La API devuelve `aviso_pii = true` y el frontend lo muestra | Es una detección por reglas, no un anonimizador certificado. No enmascara la edad, el diagnóstico ni el nombre de un centro. Un nombre sin pista ni nombre de pila común puede pasar |
| Un documento subido contiene datos personales | Aviso en la subida; modo local recomendado; se puede borrar con `DELETE /documents/{id}` | No se analiza el contenido del documento |
| Las preguntas quedan en logs del servidor o del proveedor | Recomendación de despliegue: no registrar el texto de las preguntas (solo métricas) y revisar las condiciones de retención del proveedor | Depende de la configuración del despliegue |
| Claves de API en el repositorio | `.env` y `data/` en `.gitignore`; la CI usa una clave falsa y no llama a APIs externas | — |
| Se sube por error `data/raw` o `data/chroma` | `.gitignore`; PR con checklist «sin claves ni datos sensibles» | — |

El filtro PII se puede desactivar con `PII_FILTER_ENABLED=false` (solo para pruebas).
Está cubierto por `tests/test_pii_filter.py`, incluidos casos sin falsos positivos con
preguntas normales (dosis, secciones, números de registro).

## Prompt injection

Los documentos subidos son la vía de entrada: un PDF puede incluir texto del tipo
«ignora las instrucciones anteriores». Medidas previstas en el diseño (su cumplimiento
se comprueba con `eval_generation`, ver más abajo):

1. El prompt de sistema (P3) ordena responder solo con el contexto e ignorar instrucciones
   que vengan dentro de los documentos.
2. Temperatura 0.
3. Validación posterior: cada cita `[n]` debe corresponder a un fragmento realmente
   recuperado; si no, se descarta o se marca.
4. Evaluación: el golden set incluye intentos de extraer el prompt (Q39) y de saltarse el
   grounding (Q40), y `eval_generation` comprueba que la respuesta no contiene frases de
   fuga.

Estas medidas reducen el riesgo, no lo eliminan. Un documento malicioso podría aún
condicionar el estilo de una respuesta, y por eso la fuente siempre se muestra.

## Explicabilidad y linaje del dato

Toda respuesta cita medicamento, sección, página y enlace directo a la sección en CIMA.
Los metadatos de cada fragmento (`nregistro`, `seccion`, `pagina_inicio`, `url_fuente`,
`fecha_revision`) viajan desde la ingesta hasta el panel de fuentes del frontend, de modo
que el profesional puede comprobar el dato en el documento oficial. Si no hay información
relevante, el sistema lo dice («no consta en las fichas consultadas») en lugar de
inventarla, y esa respuesta se muestra visualmente distinta.

## Calidad y vigencia de los datos

- **Vigencia**: las fichas cambian. Cada fragmento guarda la fecha de revisión (sección 10)
  cuando existe, y se muestra en la fuente. El índice refleja el momento de la descarga.
- **Catálogo**: CIMA filtra por subcadena, así que buscar «morfina» podía devolver una
  ficha de apomorfina. `python -m scripts.auditar_catalogo` revisa las filas cuyo principio
  activo real no coincide con el buscado; conviene ejecutarlo cada vez que se regenera el
  catálogo. Las discrepancias que queden son sinónimos o sales (p. ej. eritropoyetina →
  epoetina alfa) y hay que revisarlas a mano.
- **Tablas**: las de la sección 4.8 (reacciones adversas) pueden salir desordenadas al
  extraer el PDF. Es una limitación conocida.
- **Fichas EMA con varias presentaciones**: comparten `nregistro`; la respuesta puede
  proceder de una presentación distinta a la que tiene el usuario.

## Aviso de uso no clínico

Fuera del alcance de FichaClara:

- Recomendaciones individualizadas («¿le doy esto a mi paciente?»).
- Diagnóstico o prescripción.
- Tratar datos de pacientes reales.
- Sustituir la consulta al farmacéutico o al médico.

El frontend muestra un aviso sanitario permanente, el prompt lo prohíbe y hay preguntas de
este tipo en el golden set. Aun así, el sistema puede equivocarse: la información debe
verificarse siempre en la fuente citada.
