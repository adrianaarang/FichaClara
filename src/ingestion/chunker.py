"""Chunking por sección de ficha técnica + troceo recursivo dentro de secciones largas.

Responsable: P1 · Ingesta y chunking
"""

# TODO:
#   - detectar encabezados numerados (1., 4.2, 4.5, 6.6...)
#   - un chunk por sección si cabe
#   - secciones largas: RecursiveCharacterTextSplitter con overlap SOLO dentro de la sección
#   - fallback genérico para documentos subidos que no son fichas técnicas
#   - rellenar ChunkMetadata
