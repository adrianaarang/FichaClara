"""Tests de las métricas de retrieval, con retrievers falsos (sin embeddings)."""

import json
from itertools import pairwise
from pathlib import Path

import pytest

from evaluation import eval_retrieval as er
from src.common.schemas import Chunk, ChunkMetadata, RetrievedChunk

FIXTURE = Path(__file__).parent / "fixtures" / "chunks_muestra.jsonl"


def _rc(nregistro: str, seccion: str, score: float = 0.9) -> RetrievedChunk:
    meta = ChunkMetadata(
        chunk_id=f"FT_{nregistro}::{seccion}::1",
        doc_id=f"FT_{nregistro}",
        tipo_documento="ficha_tecnica",
        nombre="Med",
        nregistro=nregistro,
        seccion=seccion,
        pagina_inicio=1,
        pagina_fin=1,
        orden=0,
    )
    return RetrievedChunk(chunk=Chunk(texto="texto", metadata=meta), score=score)


GOLDEN = [
    {"id": "A", "question": "q a", "answerable": True, "categoria": "con_respuesta",
     "expected_nregistro": "1", "expected_seccion": "4.5"},
    {"id": "B", "question": "q b", "answerable": True, "categoria": "con_respuesta",
     "expected_nregistro": "2", "expected_seccion": "4.2"},
    {"id": "C", "question": "q c", "answerable": True, "categoria": "con_respuesta",
     "expected_nregistro": "3", "expected_seccion": "4.1"},
    {"id": "D", "question": "q d", "answerable": False,
     "categoria": "medicamento_ausente"},
    {"id": "E", "question": "q e", "answerable": False,
     "categoria": "consejo_clinico"},
]  # fmt: skip


def _falso(respuestas: dict[str, list[RetrievedChunk]]):
    return lambda pregunta, k: respuestas.get(pregunta, [])[:k]


@pytest.fixture
def resultados():
    retriever = _falso(
        {
            # A: acierto en la posición 1
            "q a": [_rc("1", "4.5", 0.9), _rc("1", "4.2", 0.5)],
            # B: acierto en la posición 3
            "q b": [_rc("9", "4.2", 0.8), _rc("2", "4.1", 0.7), _rc("2", "4.2", 0.6)],
            # C: falla (ficha correcta, sección incorrecta)
            "q c": [_rc("3", "4.8", 0.4)],
            # D: no devuelve nada -> rechazo correcto
            "q d": [],
            # E: consejo clínico, devuelve fragmentos: no cuenta como rechazo
            "q e": [_rc("1", "4.2", 0.6)],
        }
    )
    return er.evaluar(GOLDEN, retriever, k_max=5, enmascarar_pii=False)


def test_hit_rate_y_mrr(resultados):
    m = er.calcular_metricas(resultados, k_max=5)
    assert m["n_respondibles"] == 3
    assert m["hit_rate@1"] == pytest.approx(1 / 3, abs=1e-4)
    assert m["hit_rate@3"] == pytest.approx(2 / 3, abs=1e-4)
    assert m["hit_rate@5"] == pytest.approx(2 / 3, abs=1e-4)
    assert m["mrr"] == pytest.approx((1 + 1 / 3 + 0) / 3, abs=1e-4)
    assert m["fallos"] == ["C"]


def test_acierto_de_ficha_y_de_seccion(resultados):
    m = er.calcular_metricas(resultados, k_max=5)
    assert m["acierto_medicamento@1"] == pytest.approx(2 / 3, abs=1e-4)  # A y C
    assert m["acierto_medicamento@5"] == 1.0
    # la sección del primer fragmento coincide con la esperada en A y B (aunque en B
    # el fragmento sea de otra ficha: esta métrica no mira el medicamento)
    assert m["acierto_seccion@1"] == pytest.approx(2 / 3, abs=1e-4)


def test_rechazo_solo_cuenta_categorias_de_rechazo(resultados):
    m = er.calcular_metricas(resultados)
    assert m["n_rechazo"] == 1
    assert m["rechazo_correcto"] == 1.0
    assert m["falsos_rechazos"] == 0.0


def test_por_seccion(resultados):
    m = er.calcular_metricas(resultados)
    assert m["por_seccion"]["4.5"] == {"n": 1, "hit@5": 1.0}
    assert m["por_seccion"]["4.1"] == {"n": 1, "hit@5": 0.0}


def test_umbral_descarta_fragmentos_de_baja_puntuacion(resultados):
    m = er.calcular_metricas(resultados, umbral=0.75)
    assert m["hit_rate@5"] == pytest.approx(1 / 3, abs=1e-4)  # B (0.6) se pierde
    assert m["falsos_rechazos"] == pytest.approx(1 / 3, abs=1e-4)  # C queda vacío


def test_barrido_y_mejor_umbral(resultados):
    filas = er.barrido_umbral(resultados, umbrales=[0.0, 0.5, 0.95])
    assert [f["umbral"] for f in filas] == [0.0, 0.5, 0.95]
    assert filas[-1]["hit_rate@5"] == 0.0
    assert er.mejor_umbral(filas)["umbral"] in {0.0, 0.5}


def test_evaluar_enmascara_pii_antes_de_recuperar():
    vistas = []

    def retriever(pregunta, k):
        vistas.append(pregunta)
        return []

    golden = [{"id": "P", "question": "Mi DNI es 12345678Z, ¿dosis de atenolol?",
               "answerable": True, "categoria": "con_respuesta_con_pii",
               "expected_nregistro": "1", "expected_seccion": "4.2"}]  # fmt: skip
    resultados = er.evaluar(golden, retriever, enmascarar_pii=True)
    assert "12345678Z" not in vistas[0]
    assert resultados[0].enmascarada


def test_bm25_sobre_el_fixture_encuentra_la_ficha_correcta():
    chunks = er.cargar_chunks(FIXTURE)
    retrieve = er.crear_retriever_bm25(chunks)
    devueltos = retrieve("¿Cuál es la semivida de la melatonina de Circadin?", 5)
    assert devueltos
    assert devueltos[0].chunk.metadata.nregistro == "07392003"
    assert devueltos[0].chunk.metadata.seccion == "5.2"
    assert all(a.score >= b.score for a, b in pairwise(devueltos))


def test_guardar_escribe_json_y_csv(tmp_path, resultados):
    m = er.calcular_metricas(resultados)
    rutas = er.guardar("prueba", m, resultados, None, carpeta=tmp_path)
    assert all(r.exists() for r in rutas)
    assert (
        json.loads(rutas[0].read_text(encoding="utf-8"))["metricas"]["n_preguntas"] == 5
    )


def test_cargar_golden_real_es_valido():
    golden = er.cargar_golden()
    assert len(golden) >= 35
