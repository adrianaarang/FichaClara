"""Tests unitarios e integración para la cadena RAG (P3)."""

from unittest.mock import MagicMock, patch

import pytest

from src.common.config import settings
from src.common.schemas import QueryRequest, QueryResponse
from src.generation.llm_providers import get_llm
from src.generation.rag_chain import RAGChain


def test_rag_chain_answer_basic():
    # Crear un mock del LLM para no depender de Ollama o red en CI/CD
    mock_llm = MagicMock()
    mock_response = MagicMock()
    mock_response.content = "La dosis recomendada es 1g cada 8 horas [1]."
    mock_llm.invoke.return_value = mock_response

    with patch("src.generation.rag_chain.get_llm", return_value=(mock_llm, "ollama/mock")):
        chain = RAGChain()
        request = QueryRequest(pregunta="¿Cuál es la dosis recomendada de paracetamol?", k=4)
        response = chain.answer(request)

        assert isinstance(response, QueryResponse)
        assert response.encontrado is True
        assert len(response.fuentes) > 0
        assert response.modelo == "ollama/mock"


def test_invalid_provider(monkeypatch):
    monkeypatch.setattr(settings, "LLM_PROVIDER", "invalid")
    with pytest.raises(ValueError, match="Proveedor de LLM no soportado"):
        get_llm()