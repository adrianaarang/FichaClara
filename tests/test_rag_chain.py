"""Tests de la cadena con LLM mockeado.

Responsable: P3 · Orquestación LLM y API
"""

# TODO:

from src.generation.rag_chain import RAGChain
from src.generation.prompts import SystemPrompt
from src.generation.llm_providers import GroqProvider
from src.common.schemas import BaseSchema

def test_rag_chain():
    system_prompt = SystemPrompt()
    llm_provider = GroqProvider("dummy_key")
    rag_chain = RAGChain(system_prompt, llm_provider)

    response = rag_chain.answer("Test question")
    assert response.found == True
    assert response.answer != ""
    assert response.sources != []

def test_invalid_provider():
    from src.generation.llm_providers import get_llm_provider
    import os
    os.environ["LLM_PROVIDER"] = "invalid"
    try:
        get_llm_provider()
        assert False
    except ValueError:
        assert True