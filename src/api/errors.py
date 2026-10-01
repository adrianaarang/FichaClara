"""Manejo de excepciones → respuestas HTTP claras.

Responsable: P3 · Orquestación LLM y API
"""

# TODO:
#   - documento ilegible
#   - sin resultados relevantes
#   - LLM no disponible
# src/api/errors.py
import logging

from fastapi import Request, status
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Error no controlado en {request.url.path}: {exc!s}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Error interno del servidor",
            "error": str(exc)
        },
    )