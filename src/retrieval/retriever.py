"""Retriever: top-k + umbral de relevancia + (opcional) híbrido BM25.

Responsable: P2 · Embeddings, base vectorial y retrieval
"""

# TODO:
#   - get_retriever(k)
#   - filtro por nregistro si query_parser detecta medicamento
#   - EnsembleRetriever (vectorial + BM25) como experimento
#   - devolver lista vacía si ningún chunk supera el umbral
