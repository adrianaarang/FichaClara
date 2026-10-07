# tests/test_rag_chain.py
from unittest.mock import patch

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from src.common.config import settings
from src.common.schemas import (
    Chunk,
    ChunkMetadata,
    QueryRequest,
    QueryResponse,
    RetrievedChunk,
)
from src.generation.prompts import FRASE_NO_CONSTA
from src.generation.rag_chain import RAGChain


def _recuperado(score: float = 0.92) -> RetrievedChunk:
    meta = ChunkMetadata(
        chunk_id="FT_83208::4.2::1",
        doc_id="FT_83208",
        tipo_documento="ficha_tecnica",
        nombre="Paracetamol 1g",
        nregistro="83208",
        seccion="4.2",
        titulo_seccion="Posología y administración",
        pagina_inicio=3,
        pagina_fin=3,
        orden=0,
    )
    texto = "La dosis habitual en adultos es de 1g cada 8 horas según necesidad."
    return RetrievedChunk(chunk=Chunk(texto=texto, metadata=meta), score=score)


def _llm_falso(contenido: str):
    return GenericFakeChatModel(messages=iter([AIMessage(content=contenido)]))


def _llm_que_registra(contenido: str, vistos: list[str]):
    """LLM de mentira que guarda el prompt completo que recibe."""

    def responder(prompt_value):
        vistos.append(prompt_value.to_string())
        return AIMessage(content=contenido)

    return RunnableLambda(responder)


def test_rag_chain_answer_basic():
    llm = _llm_falso("La dosis recomendada es 1g cada 8 horas [1].")
    with (
        patch("src.generation.rag_chain.retrieve", return_value=[_recuperado()]),
        patch("src.generation.rag_chain.get_llm", return_value=(llm, "ollama/mock")),
    ):
        request = QueryRequest(pregunta="¿Cuál es la dosis recomendada de paracetamol?", k=4)
        response = RAGChain().answer(request)

    assert isinstance(response, QueryResponse)
    assert response.encontrado is True
    assert "1g cada 8 horas" in response.respuesta
    assert response.modelo == "ollama/mock"
    assert response.aviso_pii is False
    assert len(response.fuentes) == 1
    fuente = response.fuentes[0]
    assert (fuente.indice, fuente.doc_id, fuente.seccion, fuente.pagina) == (1, "FT_83208", "4.2", 3)
    assert fuente.score == 0.92


def test_sin_contexto_no_llama_al_llm():
    with (
        patch("src.generation.rag_chain.retrieve", return_value=[]),
        patch("src.generation.rag_chain.get_llm") as get_llm,
    ):
        response = RAGChain().answer(QueryRequest(pregunta="¿Cuál es la capital de Francia?"))

    get_llm.assert_not_called()
    assert response.encontrado is False
    assert response.respuesta == FRASE_NO_CONSTA
    assert response.fuentes == []
    assert response.modelo is None


def test_el_retriever_recibe_k_de_la_peticion_o_el_por_defecto():
    with (
        patch("src.generation.rag_chain.retrieve", return_value=[]) as retrieve,
    ):
        RAGChain().answer(QueryRequest(pregunta="¿Para qué sirve el Januvia?", k=3))
        RAGChain().answer(QueryRequest(pregunta="¿Para qué sirve el Januvia?"))

    assert retrieve.call_args_list[0].kwargs["k"] == 3
    assert retrieve.call_args_list[1].kwargs["k"] == settings.RETRIEVER_K


def test_los_datos_personales_no_llegan_ni_al_retriever_ni_al_llm():
    """Usa el filtro PII real (P5): el DNI se enmascara antes de buscar y antes del LLM."""
    pregunta = "Paciente con DNI 12345678Z: ¿cuál es la dosis de paracetamol?"
    prompts: list[str] = []
    llm = _llm_que_registra("1g cada 8 horas [1].", prompts)
    with (
        patch("src.generation.rag_chain.retrieve", return_value=[_recuperado()]) as retrieve,
        patch("src.generation.rag_chain.get_llm", return_value=(llm, "groq/mock")),
    ):
        response = RAGChain().answer(QueryRequest(pregunta=pregunta))

    assert response.aviso_pii is True
    assert "12345678Z" not in retrieve.call_args.args[0]
    assert "[DATO]" in retrieve.call_args.args[0]
    assert len(prompts) == 1
    assert "12345678Z" not in prompts[0]
    assert "dosis de paracetamol" in prompts[0]


def test_aviso_pii_tambien_cuando_no_hay_contexto():
    with patch("src.generation.rag_chain.retrieve", return_value=[]):
        response = RAGChain().answer(QueryRequest(pregunta="Mi DNI es 12345678Z, ¿hola?"))

    assert response.encontrado is False
    assert response.aviso_pii is True


def test_las_citas_a_fuentes_inexistentes_se_eliminan():
    llm = _llm_falso("Es 1g cada 8 horas [1] y además algo inventado [7].")
    with (
        patch("src.generation.rag_chain.retrieve", return_value=[_recuperado()]),
        patch("src.generation.rag_chain.get_llm", return_value=(llm, "ollama/mock")),
    ):
        response = RAGChain().answer(QueryRequest(pregunta="¿Cuál es la dosis de paracetamol?"))

    assert "[1]" in response.respuesta
    assert "[7]" not in response.respuesta


def test_las_citas_con_corchetes_asiaticos_se_normalizan():
    """gpt-oss cita 【1】 o 【1†L3-L5】: se convierten a [1], y las fantasma se eliminan igual."""
    llm = _llm_falso("Son 3,5-4 horas【1】 y algo inventado【7†L2-L4】.")
    with (
        patch("src.generation.rag_chain.retrieve", return_value=[_recuperado()]),
        patch("src.generation.rag_chain.get_llm", return_value=(llm, "groq/openai/gpt-oss-120b")),
    ):
        response = RAGChain().answer(QueryRequest(pregunta="¿Cuál es la semivida de la melatonina?"))

    assert response.respuesta == "Son 3,5-4 horas[1] y algo inventado."
    assert "【" not in response.respuesta


def test_error_del_llm_devuelve_respuesta_controlada():
    with (
        patch("src.generation.rag_chain.retrieve", return_value=[_recuperado()]),
        patch("src.generation.rag_chain.get_llm", side_effect=RuntimeError("sin conexión")),
    ):
        response = RAGChain().answer(QueryRequest(pregunta="¿Cuál es la dosis de paracetamol?"))

    assert response.encontrado is False
    assert response.fuentes == []
    assert "Error temporal" in response.respuesta
