"""Tests de integración para los endpoints de FastAPI (P3)."""

from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}


def test_ingest():
    response = client.post(
        "/ingest",
        json={"doc_id": "doc_test", "nombre": "Documento Test"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "doc_id" in data
    assert "chunks" in data


def test_get_documents():
    response = client.get("/documents")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_query():
    # Usar 'pregunta' según QueryRequest en schemas.py
    response = client.post(
        "/query",
        json={"pregunta": "¿Cuál es la dosis de paracetamol?", "k": 3},
    )
    assert response.status_code == 200
    data = response.json()
    assert "respuesta" in data
    assert "encontrado" in data
    assert "fuentes" in data