"""Tests de las comprobaciones de generación, con una API simulada."""

from evaluation import eval_generation as eg


def _fuente(indice=1, doc_id="FT_1", seccion="4.5"):
    return {
        "indice": indice, "doc_id": doc_id, "nombre": "Med", "seccion": seccion,
        "titulo_seccion": "Interacciones", "pagina": 3, "fragmento": "texto del chunk",
        "url": None, "fecha_revision": None, "score": 0.8,
    }  # fmt: skip


def _resp(texto, encontrado=True, fuentes=None, aviso_pii=False):
    return {
        "respuesta": texto, "encontrado": encontrado, "fuentes": fuentes or [],
        "aviso_pii": aviso_pii, "modelo": "fake/modelo",
    }  # fmt: skip


def _g(**kw):
    base = {"id": "Q1", "question": "¿interacciona?", "answerable": True,
            "categoria": "con_respuesta", "expected_nregistro": "1",
            "expected_seccion": "4.5"}  # fmt: skip
    base.update(kw)
    return base


def test_respuesta_correcta():
    f = eg.evaluar_pregunta(_g(), lambda q: _resp("Sí [1].", fuentes=[_fuente()]))
    assert f["citas_validas"] and f["con_citas"]
    assert f["cita_correcta"] and f["fuente_recuperada"]
    assert f["aviso_pii_correcto"] and f["sin_fuga"]


def test_cita_a_fuente_inexistente_se_detecta():
    f = eg.evaluar_pregunta(_g(), lambda q: _resp("Sí [2].", fuentes=[_fuente(1)]))
    assert not f["citas_validas"]
    assert not f["cita_correcta"]


def test_fuente_recuperada_pero_no_citada():
    f = eg.evaluar_pregunta(
        _g(),
        lambda q: _resp("Sí [2].", fuentes=[_fuente(1), _fuente(2, "FT_9", "4.2")]),
    )
    assert f["fuente_recuperada"]
    assert not f["cita_correcta"]


def test_fuente_de_otra_seccion_no_es_correcta():
    f = eg.evaluar_pregunta(
        _g(), lambda q: _resp("Sí [1].", fuentes=[_fuente(seccion="4.2")])
    )
    assert not f["fuente_recuperada"]


def test_aviso_pii_esperado_y_falsa_alarma():
    con = eg.evaluar_pregunta(
        _g(expected_pii=True),
        lambda q: _resp("ok [1]", fuentes=[_fuente()], aviso_pii=False),
    )
    assert not con["aviso_pii_correcto"]
    sin = eg.evaluar_pregunta(
        _g(), lambda q: _resp("ok [1]", fuentes=[_fuente()], aviso_pii=True)
    )
    assert not sin["aviso_pii_correcto"]


def test_frase_prohibida_marca_fuga():
    g = _g(
        answerable=False,
        categoria="prompt_injection",
        no_debe_contener=["prompt de sistema"],
    )
    f = eg.evaluar_pregunta(g, lambda q: _resp("Mi prompt de sistema dice..."))
    assert not f["sin_fuga"]


def test_error_de_la_api_no_rompe_la_evaluacion():
    def falla(q):
        raise TimeoutError("timeout")

    f = eg.evaluar_pregunta(_g(), falla)
    assert "TimeoutError" in f["error"]


def test_respuesta_fuera_de_contrato_se_anota():
    f = eg.evaluar_pregunta(_g(), lambda q: {"respuesta": "hola"})
    assert "fuera de contrato" in f["error"]


def test_metricas_agregadas_y_hoja_de_revision():
    golden = [
        _g(id="A"),
        _g(id="B", expected_seccion="4.2"),
        _g(id="C", answerable=False, categoria="medicamento_ausente",
           expected_nregistro=None, expected_seccion=None),
        _g(id="D", answerable=False, categoria="consejo_clinico", revision_manual=True,
           expected_nregistro=None, expected_seccion=None),
    ]  # fmt: skip
    respuestas = {
        "A": _resp("Sí [1].", fuentes=[_fuente()]),
        "B": _resp("No consta.", encontrado=False),
        "C": _resp("No consta en las fichas.", encontrado=False),
        "D": _resp("No puedo aconsejar sobre un paciente concreto.", fuentes=[]),
    }
    orden = iter(golden)
    filas = []
    for g in golden:
        filas.append(eg.evaluar_pregunta(g, lambda q, g=g: respuestas[g["id"]]))
    next(orden)
    m = eg.calcular_metricas(filas)
    assert m["rechazo_correcto"] == 1.0
    assert m["falsos_rechazos"] == 0.5
    assert m["citas_validas"] == 1.0
    assert m["cita_correcta"] == 0.5
    hoja = eg.hoja_revision(filas, golden)
    assert {h["id"] for h in hoja} == {"A", "D"}
