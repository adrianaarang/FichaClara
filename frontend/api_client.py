# File: frontend/api_client.py

import os
from typing import Any

import requests

API_URL = os.getenv("API_URL", "http://localhost:8000")

def ask_question(query: str) -> dict[str, Any]:
    """
    Sends natural language query to the FastAPI RAG endpoint (/api/query).
    Enforces graceful degradation on connection failure.
    """
    endpoint = f"{API_URL}/api/query"
    payload = {"query": query}

    try:
        response = requests.post(endpoint, json=payload, timeout=30)
        
        if response.status_code == 200:
            return response.json()
        elif response.status_code == 422:
            return {
                "found": False,
                "error": "VALIDATION_ERROR",
                "answer": "La consulta no cumple con los requisitos mínimos de formato.",
                "sources": []
            }
        else:
            return {
                "found": False,
                "error": f"HTTP_{response.status_code}",
                "answer": f"Error del servidor al procesar la consulta ({response.status_code}).",
                "sources": []
            }

    except requests.exceptions.ConnectionError:
        return {
            "found": False,
            "error": "CONNECTION_REFUSED",
            "answer": "No se pudo conectar con el servidor backend de FichaClara (FastAPI). Verifica que el servicio esté ejecutándose en " + API_URL,
            "sources": []
        }
    except requests.exceptions.Timeout:
        return {
            "found": False,
            "error": "TIMEOUT",
            "answer": "La consulta tardó demasiado tiempo en responder. Inténtalo de nuevo.",
            "sources": []
        }