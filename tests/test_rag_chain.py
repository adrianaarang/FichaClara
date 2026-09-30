"""Tests unitarios e integración para la cadena RAG (P3)."""

import pytest

from src.common.config import settings
from src.common.schemas import QueryRequest, QueryResponse
from src.generation.llm_providers import get_llm
from src.generation.rag_chain import RAGChain


def test_rag_chain_answer_basic():
    chain = RAGChain()
    request = QueryRequest(pregunta="¿Cuál es la dosis recomendada de paracetamol?", k=4)
    response = chain.answer(request)

    assert isinstance(response, QueryResponse)
    assert response.encontrado is True
    assert len(response.fuentes) > 0


def test_invalid_provider(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "invalid")
    with pytest.raises(ValueError, match="Proveedor de LLM no soportado"):
        get_llm()