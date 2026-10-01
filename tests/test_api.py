# tests/test_api.py
from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200

def test_ingest():
    response = client.post(
        "/ingest",
        json={"doc_id": "doc_test", "nombre": "Documento Test"},
    )
    assert response.status_code == 200

def test_get_documents():
    response = client.get("/documents")
    assert response.status_code == 200