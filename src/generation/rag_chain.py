"""Cadena LangChain (LCEL): retriever → prompt → LLM → respuesta + fuentes.

Responsable: P3 · Orquestación LLM y API
"""

import re

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


# --- FakeRetriever para pruebas iniciales hasta que P2 entregue ---
def fake_retrieve(pregunta: str, k: int = 4) -> list[RetrievedChunk]:
    # Mock que simula la respuesta de David (P2)
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


# --- MOCK PII hasta que P5 entregue ---
def fake_check_pii(pregunta: str) -> PiiResult:
    return PiiResult(contiene_pii=False, tipos=[], texto_enmascarado=pregunta)


class RAGChain:
    def __init__(self):
        pass

    def answer(self, request: QueryRequest) -> QueryResponse:
        # 1. Filtro PII (Yohana - P5)
        pii_res = fake_check_pii(request.pregunta)
        texto_pregunta = (
            pii_res.texto_enmascarado
            if pii_res.contiene_pii
            else request.pregunta
        )

        # 2. Retrieval (David - P2 / FakeRetriever)
        k_val = request.k if request.k is not None else settings.RETRIEVER_K
        retrieved = fake_retrieve(texto_pregunta, k=k_val)

        # Criterio de Aceptación: Sin contexto -> encontrado=False sin llamar al LLM
        if not retrieved:
            return QueryResponse(
                respuesta=FRASE_NO_CONSTA,
                encontrado=False,
                fuentes=[],
                aviso_pii=pii_res.contiene_pii,
                modelo=None,
            )

        # 3. Mapear Chunks a Fuentes para P4 (Anas)
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

        # 4. Invocar LLM con manejo de excepciones (timeouts/caídas)
        try:
            llm, model_name = get_llm()
            contexto_str = formatear_contexto(fuentes)
            prompt_value = RAG_PROMPT.format_messages(
                contexto=contexto_str, pregunta=texto_pregunta
            )
            response_message = llm.invoke(prompt_value)
            respuesta_texto = str(response_message.content)
        except Exception:  # noqa: BLE001
            return QueryResponse(
                respuesta="Error temporal al consultar el modelo de lenguaje.",
                encontrado=False,
                fuentes=[],
                aviso_pii=pii_res.contiene_pii,
                modelo=None,
            )

        # 5. Validación posterior de citas [n]: eliminar citas fantasmas que no existan
        indices_validos = {f.indice for f in fuentes}

        def filtrar_cita(match):
            idx = int(match.group(1))
            return match.group(0) if idx in indices_validos else ""

        respuesta_limpia = re.sub(r"\[(\d+)\]", filtrar_cita, respuesta_texto)

        return QueryResponse(
            respuesta=respuesta_limpia,
            encontrado=True,
            fuentes=fuentes,
            aviso_pii=pii_res.contiene_pii,
            modelo=model_name,
        )