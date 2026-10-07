# File: frontend/mock_api.py

import time
from typing import Any


def ask_question(query: str) -> dict[str, Any]:
    """
    Simulates the RAG backend responses across all key test scenarios.
    Type specific keywords into the chat to trigger each scenario:
    - 'unsupported' or 'desconocido' -> No-result state (found=False)
    - 'error'                       -> Server / API failure
    - 'paciente' or 'maria'         -> PII violation error
    - Any other query               -> Grounded success state
    """
    time.sleep(1.2)  # Realistic retrieval & generation latency
    q = query.lower()

    # SCENARIO 6: PII Warning Triggered
    if any(k in q for k in ["paciente", "maria", "dni", "historia clínica"]):
        return {
            "found": False,
            "error": "PII_DETECTED",
            "answer": "⚠️ Aviso de privacidad: Se han detectado posibles datos de carácter personal. Por seguridad, no introduzcas nombres de pacientes ni identificadores sanitarios.",
            "sources": []
        }

    # SCENARIO 7: API / System Error
    if "error" in q:
        return {
            "found": False,
            "error": "SYSTEM_ERROR",
            "answer": "FichaClara no está disponible temporalmente. Por favor, inténtalo de nuevo en unos minutos.",
            "sources": []
        }

    # SCENARIO 2: No-result state (Information not found in indexed docs)
    if any(k in q for k in ["desconocido", "unsupported", "paracetamol infantil", "dosis perro"]):
        return {
            "found": False,
            "answer": "Información no encontrada en las fichas técnicas indexadas en este catálogo.",
            "sources": []
        }

    # SCENARIO 1: Successful grounded response with section & CIMA metadata
    return {
        "found": True,
        "answer": (
            "El ibuprofeno puede potenciar el efecto de los anticoagulantes orales como el acenocumarol "
            "(Sintrom), aumentando el riesgo de hemorragia gastrointestinal y complicaciones hemorrágicas. "
            "Si no puede evitarse su uso concomitante, se deben monitorizar estrechamente los parámetros de coagulación (INR)."
        ),
        "sources": [
            {
                "medicine": "IBUPROFENO KERN PHARMA 600 mg comprimidos recubiertos",
                "section": "4.5 Interacción con otros medicamentos y otras formas de interacción",
                "page": 7,
                "fragment": (
                    "Anticoagulantes: los AINE pueden aumentar los efectos de los anticoagulantes, "
                    "como el acenocumarol o la warfarina. En caso de tratamiento combinado, "
                    "se aconseja realizar controles periódicos de la coagulación."
                ),
                "revision_date": "Mayo 2023",
                "cima_url": "https://cima.aemps.es/cima/dochtml/ft/64745/FT_64745.html#4-5-interacciones-con-otros-medicamentos-y-otras-formas-de-interacci-n"
            }
        ]
    }

