"""Cadena LangChain (LCEL): retriever → prompt → LLM → respuesta + fuentes.

Responsable: P3 · Orquestación LLM y API
"""

# TODO:
#   - answer(question) -> QueryResponse
#   - si retriever vacío: no llamar al LLM, devolver found=False
#   - timeouts y errores del proveedor
