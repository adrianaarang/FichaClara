# src/generation/rag_chain.py
import re
import logging
from typing import Any

from langchain_core.output_parsers import StrOutputParser

from src.common.config import settings
from src.common.schemas import (
    Chunk,
    ChunkMetadata,
    Fuente,
    PiiResult,
    QueryRequest,
    QueryResponse,
    RetrievedChunk,
)
from src.generation.llm_providers import get_llm
from src.generation.prompts import FRASE_NO_CONSTA, RAG_PROMPT, formatear_contexto

logger = logging.getLogger(__name__)


def fake_retrieve(pregunta: str, k: int = 4) -> list[RetrievedChunk]:
    meta = ChunkMetadata(
        chunk_id="FT_1234::4.2::1",
        doc_id="FT_1234",
        tipo_documento="ficha_tecnica",
        nombre="Paracetamol 1g",
        seccion="4.2",
        titulo_seccion="Posología y administración",
        pagina_inicio=1,
        pagina_fin=1,
        orden=0,
    )
    chunk = Chunk(
        texto="La dosis habitual en adultos es de 1g cada 8 horas según necesidad.",
        metadata=meta,
    )
    return [RetrievedChunk(chunk=chunk, score=0.92)]


def fake_check_pii(pregunta: str) -> PiiResult:
    return PiiResult(contiene_pii=False, tipos=[], texto_enmascarado=pregunta)


class RAGChain:
    def __init__(self) -> None:
        pass

    def _mapear_fuentes(self, retrieved: list[RetrievedChunk]) -> list[Fuente]:
        fuentes: list[Fuente] = []
        for idx, r_chunk in enumerate(retrieved, start=1):
            meta = r_chunk.chunk.metadata
            fuentes.append(
                Fuente(
                    indice=idx,
                    doc_id=meta.doc_id,
                    nombre=meta.nombre,
                    seccion=meta.seccion,
                    titulo_seccion=meta.titulo_seccion,
                    pagina=meta.pagina_inicio,
                    fragmento=r_chunk.chunk.texto,
                    url=meta.url_fuente,
                    fecha_revision=meta.fecha_revision,
                    score=r_chunk.score,
                )
            )
        return fuentes

    def _limpiar_citas_fantasmas(self, respuesta: str, indices_validos: set[int]) -> str:
        def filtrar_cita(match: re.Match) -> str:
            idx = int(match.group(1))
            return match.group(0) if idx in indices_validos else ""

        return re.sub(r"\[(\d+)\]", filtrar_cita, respuesta)

    def answer(self, request: QueryRequest) -> QueryResponse:
        # 1. Filtro PII
        pii_res = fake_check_pii(request.pregunta)
        texto_pregunta = (
            pii_res.texto_enmascarado
            if pii_res.contiene_pii
            else request.pregunta
        )

        # 2. Retrieval
        k_val = request.k if request.k is not None else settings.RETRIEVER_K
        retrieved = fake_retrieve(texto_pregunta, k=k_val)

        # Criterio de Aceptación: Sin contexto -> no invocar LLM
        if not retrieved:
            return QueryResponse(
                respuesta=FRASE_NO_CONSTA,
                encontrado=False,
                fuentes=[],
                aviso_pii=pii_res.contiene_pii,
                modelo=None,
            )

        # 3. Preparación de fuentes e insumos para el Prompt
        fuentes = self._mapear_fuentes(retrieved)
        contexto_str = formatear_contexto(fuentes)

        # 4. Construcción y Ejecución de Cadena LCEL
        try:
            llm, model_name = get_llm()
            
            # Composición de Cadena Declarativa LCEL
            chain = RAG_PROMPT | llm | StrOutputParser()
            
            respuesta_texto = chain.invoke({
                "contexto": contexto_str,
                "pregunta": texto_pregunta
            })
        except Exception as exc:
            logger.error(f"Error al invocar la cadena LCEL: {exc}", exc_info=True)
            return QueryResponse(
                respuesta="Error temporal al consultar el modelo de lenguaje.",
                encontrado=False,
                fuentes=[],
                aviso_pii=pii_res.contiene_pii,
                modelo=None,
            )

        # 5. Post-procesamiento
        indices_validos = {f.indice for f in fuentes}
        respuesta_limpia = self._limpiar_citas_fantasmas(respuesta_texto, indices_validos)

        return QueryResponse(
            respuesta=respuesta_limpia,
            encontrado=True,
            fuentes=fuentes,
            aviso_pii=pii_res.contiene_pii,
            modelo=model_name,
        )