"""Flujo completo sin red ni modelos descargados.

API (P3) → filtro PII (P5) → query parser + retriever (P2) → ChromaDB real → LLM falso,
y la ingesta de documentos (P1) escribiendo en ese mismo índice. Lo único simulado son los
embeddings (bolsa de palabras con hash) y el LLM.

Responsable: P3 · Orquestación LLM y API
"""
import hashlib
import math
import re
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from langchain_chroma import Chroma
from langchain_core.embeddings import Embeddings
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from src.api.main import app
from src.common.schemas import Chunk, ChunkMetadata
from src.indexing.vector_store import add_chunks
from src.retrieval.retriever import retrieve as retrieve_real

CATALOGO = Path(__file__).resolve().parents[1] / "data" / "catalogo_medicamentos.csv"

client = TestClient(app)


class EmbeddingsFalsos(Embeddings):
    """Textos que comparten palabras quedan cerca (coseno). Sin modelos ni red."""

    DIM = 64

    def _vector(self, texto: str) -> list[float]:
        v = [0.0] * self.DIM
        for palabra in re.findall(r"\w+", texto.lower()):
            v[int(hashlib.md5(palabra.encode()).hexdigest(), 16) % self.DIM] += 1.0
        norma = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norma for x in v]

    def embed_documents(self, textos: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in textos]

    def embed_query(self, texto: str) -> list[float]:
        return self._vector(texto)


def _chunk_ficha(nregistro: str, nombre: str, texto: str) -> Chunk:
    meta = ChunkMetadata(
        chunk_id=f"FT_{nregistro}::4.2::1",
        doc_id=f"FT_{nregistro}",
        tipo_documento="ficha_tecnica",
        nombre=nombre,
        nregistro=nregistro,
        seccion="4.2",
        titulo_seccion="Posología y forma de administración",
        pagina_inicio=2,
        pagina_fin=2,
        orden=0,
    )
    return Chunk(texto=texto, metadata=meta)


@pytest.fixture
def indice(tmp_path):
    """Chroma real en una carpeta temporal con dos fichas del catálogo ya indexadas."""
    almacen = Chroma(
        collection_name="test_integracion",
        embedding_function=EmbeddingsFalsos(),
        persist_directory=str(tmp_path / "chroma"),
        collection_metadata={"hnsw:space": "cosine"},
    )
    with (
        patch("src.indexing.vector_store.get_vector_store", return_value=almacen),
        patch("src.retrieval.retriever.get_vector_store", return_value=almacen),
        # El umbral lo calibra P2 en su .env: aquí se fija a None para que el test no dependa de él.
        patch(
            "src.generation.rag_chain.retrieve",
            side_effect=lambda q, k: retrieve_real(q, k=k, relevance_threshold=None, catalog_path=CATALOGO),
        ),
    ):
        add_chunks([
            _chunk_ficha("83208", "ANTIDOL INFANTIL 100 MG/ML SOLUCION ORAL",
                         "La dosis de paracetamol en niños es de 10 a 15 mg por kg cada 6 u 8 horas."),
            _chunk_ficha("74559", "DIFENADOL RAPID 400 mg GRANULADO PARA SOLUCION ORAL",
                         "La dosis de ibuprofeno en adultos es de 400 mg cada 6 u 8 horas."),
        ])
        yield almacen


def _llm_que_registra(contenido: str, prompts: list[str]):
    def responder(prompt_value):
        prompts.append(prompt_value.to_string())
        return AIMessage(content=contenido)

    return RunnableLambda(responder)


def _preguntar(pregunta: str, llm) -> dict:
    with patch("src.generation.rag_chain.get_llm", return_value=(llm, "fake/mock")):
        response = client.post("/query", json={"pregunta": pregunta})
    assert response.status_code == 200
    return response.json()


def test_pregunta_sobre_un_medicamento_cita_solo_su_ficha(indice):
    prompts: list[str] = []
    llm = _llm_que_registra("La dosis en niños es de 10 a 15 mg/kg [1].", prompts)

    cuerpo = _preguntar("¿Cuál es la dosis de paracetamol?", llm)

    assert cuerpo["encontrado"] is True
    assert cuerpo["modelo"] == "fake/mock"
    assert {f["doc_id"] for f in cuerpo["fuentes"]} == {"FT_83208"}  # el filtro por nregistro funciona
    assert cuerpo["fuentes"][0]["seccion"] == "4.2"
    assert "ibuprofeno" not in prompts[0].lower()  # al LLM solo le llega su ficha


def test_los_datos_personales_no_llegan_ni_a_chroma_ni_al_llm(indice):
    prompts: list[str] = []
    llm = _llm_que_registra("10 a 15 mg/kg [1].", prompts)

    with patch.object(
        indice, "similarity_search_with_relevance_scores", wraps=indice.similarity_search_with_relevance_scores
    ) as buscar:
        cuerpo = _preguntar("Paciente con DNI 12345678Z: ¿cuál es la dosis de paracetamol?", llm)

    assert cuerpo["aviso_pii"] is True
    assert cuerpo["encontrado"] is True
    assert "12345678Z" not in buscar.call_args.args[0]
    assert "12345678Z" not in prompts[0]


@pytest.mark.parametrize(
    "pregunta",
    [
        "¿Cuál es la dosis de sildenafilo?",  # medicamento fuera del catálogo
        "¿Cuál es la capital de Francia?",  # sin ningún medicamento
    ],
)
def test_sin_medicamento_del_catalogo_no_se_llama_al_llm(indice, pregunta):
    with patch("src.generation.rag_chain.get_llm") as get_llm:
        response = client.post("/query", json={"pregunta": pregunta})

    get_llm.assert_not_called()
    cuerpo = response.json()
    assert cuerpo["encontrado"] is False
    assert cuerpo["fuentes"] == []


def test_ciclo_de_vida_de_un_documento_subido(indice):
    guia = (
        "# Guía de insulina\n\n## Conservación\n\nLas plumas sin abrir se guardan en nevera.\n\n"
        "## Administración\n\nLa inyección subcutánea se rota entre abdomen y muslos.\n"
    ).encode()

    # 1. Se sube: P1 lo trocea y se indexa en el mismo Chroma que consulta el retriever.
    subida = client.post("/ingest", files={"file": ("guia_insulina.md", guia, "text/markdown")})
    assert subida.status_code == 200
    doc = subida.json()
    assert doc["ya_existia"] is False and doc["chunks"] > 0

    # 2. Aparece en /documents junto a las fichas, con su nº de fragmentos.
    listado = {d["doc_id"]: d for d in client.get("/documents").json()}
    assert set(listado) == {"FT_83208", "FT_74559", doc["doc_id"]}
    assert listado[doc["doc_id"]]["chunks"] == doc["chunks"]
    assert listado["FT_83208"]["tipo_documento"] == "ficha_tecnica"

    # 3. Volver a subirlo lo reemplaza: no se duplican fragmentos.
    de_nuevo = client.post("/ingest", files={"file": ("guia_insulina.md", guia, "text/markdown")}).json()
    assert de_nuevo["ya_existia"] is True and de_nuevo["doc_id"] == doc["doc_id"]
    chunks_en_chroma = indice.get(where={"doc_id": doc["doc_id"]})["ids"]
    assert len(chunks_en_chroma) == doc["chunks"]

    # 4. Se borra: desaparece del listado y borrar otra vez da 404.
    borrado = client.delete(f"/documents/{doc['doc_id']}")
    assert borrado.status_code == 200 and borrado.json()["chunks_eliminados"] == doc["chunks"]
    assert doc["doc_id"] not in {d["doc_id"] for d in client.get("/documents").json()}
    assert client.delete(f"/documents/{doc['doc_id']}").status_code == 404
