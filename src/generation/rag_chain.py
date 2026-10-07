# src/generation/rag_chain.py
import logging
import re

from langchain_core.output_parsers import StrOutputParser

from src.common.config import settings
from src.common.schemas import (
    Fuente,
    QueryRequest,
    QueryResponse,
    RetrievedChunk,
)
from src.generation.llm_providers import get_llm
from src.generation.prompts import FRASE_NO_CONSTA, RAG_PROMPT, formatear_contexto
from src.guardrails.pii_filter import check_pii  # P5: filtro de datos personales
from src.retrieval.retriever import retrieve  # P2: búsqueda en ChromaDB

logger = logging.getLogger(__name__)

# Algunos modelos (p. ej. gpt-oss de Groq) citan con corchetes asiáticos, 【1】 o 【1†L3-L5】,
# en vez de [1]. El frontend y la validación de citas solo entienden [n].
_RE_CITA_ASIATICA = re.compile(r"【\s*(\d+)[^】]*】")


def normalizar_citas(texto: str) -> str:
    """Convierte 【n】 (y 【n†...】) en [n], sea cual sea el modelo que haya respondido."""
    return _RE_CITA_ASIATICA.sub(r"[\1]", texto)


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
        pii_res = check_pii(request.pregunta)
        texto_pregunta = (
            pii_res.texto_enmascarado
            if pii_res.contiene_pii
            else request.pregunta
        )

        # 2. Retrieval (siempre con la pregunta ya enmascarada)
        k_val = request.k if request.k is not None else settings.RETRIEVER_K
        retrieved = retrieve(texto_pregunta, k=k_val)

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
        except Exception:
            logger.exception("Error al invocar la cadena LCEL")
            return QueryResponse(
                respuesta="Error temporal al consultar el modelo de lenguaje.",
                encontrado=False,
                fuentes=[],
                aviso_pii=pii_res.contiene_pii,
                modelo=None,
            )

        # 5. Post-procesamiento
        indices_validos = {f.indice for f in fuentes}
        respuesta_limpia = self._limpiar_citas_fantasmas(normalizar_citas(respuesta_texto), indices_validos)

        return QueryResponse(
            respuesta=respuesta_limpia,
            encontrado=True,
            fuentes=fuentes,
            aviso_pii=pii_res.contiene_pii,
            modelo=model_name,
        )