"""Tests de endpoints con TestClient.

Responsable: P3 · Orquestación LLM y API
"""

# TODO:

from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}

def test_ingest():
    response = client.post("/ingest", json={"id": "1", "content": "Sample document"})
    assert response.status_code == 200
    assert response.json() == {"status": "ingested", "document_id": "1"}

def test_get_documents():
    response = client.get("/documents")
    assert response.status_code == 200
    assert response.json() == {"documents": []}

def test_delete_document():
    response = client.delete("/documents/1")
    assert response.status_code == 200
    assert response.json() == {"status": "deleted", "document_id": "1"}

def test_query():
    response = client.post("/query", json={"question": "Test question"})
    assert response.status_code == 200
    assert response.json()["found"] == True
    assert response.json()["answer"] != ""
    assert response.json()["sources"] != []