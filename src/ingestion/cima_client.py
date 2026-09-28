"""Cliente de la API REST de CIMA (https://cima.aemps.es/cima/rest/).

Responsable: P1 · Ingesta y chunking
"""

# TODO:
#   - buscar medicamento por nombre / nregistro (GET medicamentos, GET medicamento)
#   - obtener URL del PDF de ficha técnica (docs, tipo=1)
#   - descargar PDF a data/raw/ con reintentos y pausa entre peticiones
#   - (opcional) GET docSegmentado/secciones/1 para validar las secciones detectadas
