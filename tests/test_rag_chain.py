# tests/test_rag_chain.py
from unittest.mock import patch

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from src.common.schemas import QueryRequest, QueryResponse
from src.generation.rag_chain import RAGChain


def test_rag_chain_answer_basic():
    # Modelo fake nativo de langchain_core
    fake_llm = GenericFakeChatModel(
        messages=iter([AIMessage(content="La dosis recomendada es 1g cada 8 horas [1].")])
    )

    with patch("src.generation.rag_chain.get_llm", return_value=(fake_llm, "ollama/mock")):
        chain = RAGChain()
        request = QueryRequest(pregunta="¿Cuál es la dosis recomendada de paracetamol?", k=4)
        response = chain.answer(request)

        assert isinstance(response, QueryResponse)
        assert response.encontrado is True
        assert "1g cada 8 horas" in response.respuesta