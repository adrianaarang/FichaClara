"""Tests de la vinculación golden set <-> chunks."""

import json
from pathlib import Path

from evaluation import vincular_chunks as vc

FIXTURE = Path(__file__).parent / "fixtures" / "chunks_muestra.jsonl"


def _golden(tmp_path, entradas):
    ruta = tmp_path / "golden.jsonl"
    ruta.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in entradas) + "\n",
        encoding="utf-8",
    )
    return ruta


def _pregunta(id_, nregistro, seccion):
    return {"id": id_, "question": "q", "answerable": True, "categoria": "con_respuesta",
            "expected_nregistro": nregistro, "expected_seccion": seccion}  # fmt: skip


def test_indexa_los_chunks_del_fixture_por_ficha_y_seccion():
    indice = vc.indexar_chunks(FIXTURE)
    assert indice
    for (nregistro, seccion), ids in indice.items():
        assert nregistro and seccion
        assert all(i.startswith("FT_") for i in ids)


def test_vincula_y_detecta_huecos():
    indice = vc.indexar_chunks(FIXTURE)
    nregistro, seccion = next(iter(indice))
    golden = [
        _pregunta("A", nregistro, seccion),
        _pregunta("B", "99999999", "4.2"),
        {"id": "C", "question": "q", "answerable": False, "categoria": "fuera_de_alcance",
         "expected_nregistro": None, "expected_seccion": None},
    ]  # fmt: skip
    vinculado, huecos = vc.vincular(golden, indice)
    assert vinculado[0]["expected_chunk_ids"] == indice[(nregistro, seccion)]
    assert vinculado[1]["expected_chunk_ids"] == []
    assert [h["id"] for h in huecos] == ["B"]
    assert "expected_chunk_ids" not in vinculado[2]


def test_cli_escribe_y_devuelve_codigo_de_error_si_hay_huecos(tmp_path):
    indice = vc.indexar_chunks(FIXTURE)
    nregistro, seccion = next(iter(indice))
    golden = _golden(tmp_path, [_pregunta("A", nregistro, seccion)])
    assert (
        vc.main(["--golden", str(golden), "--chunks", str(FIXTURE), "--escribir"]) == 0
    )
    escrito = json.loads(golden.read_text(encoding="utf-8").splitlines()[0])
    assert escrito["expected_chunk_ids"]

    golden2 = _golden(tmp_path, [_pregunta("B", "99999999", "4.2")])
    assert vc.main(["--golden", str(golden2), "--chunks", str(FIXTURE)]) == 1
