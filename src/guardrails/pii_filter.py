"""Filtro de datos personales en la pregunta antes de enviarla a una API comercial.

Responsable: P5 · Calidad, evaluación, DevOps y documentación
"""

# TODO:
#   - detectar DNI/NIE, teléfonos, emails, nº de historia clínica y nombres propios (regex + lista)
#   - devolver aviso o texto enmascarado; configurable desde .env
#   - tests en tests/test_pii_filter.py
