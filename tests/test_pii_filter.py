"""Tests del filtro de datos personales.

Responsable: P5 · Calidad, evaluación, DevOps y documentación
"""

import pytest

from src.guardrails.pii_filter import MASCARA, _letra_dni_valida, _nie_valido, check_pii


def test_letra_dni_valida():
    assert _letra_dni_valida("12345678", "Z")
    assert not _letra_dni_valida("12345678", "A")


def test_nie_valido():
    assert _nie_valido("X1234567L")
    assert not _nie_valido("X1234567A")


@pytest.mark.parametrize(
    "texto, tipo",
    [
        ("Mi DNI es 12345678Z, ¿puedo tomar ibuprofeno?", "dni"),
        ("El DNI 12345678-Z de la residente", "dni"),
        ("NIE X1234567L en la solicitud", "nie"),
        ("Llámame al 612 345 678 si no responde", "telefono"),
        ("Teléfono +34 912345678", "telefono"),
        ("Escríbeme a ana.ruiz@correo.es por favor", "email"),
        ("Paciente con NHC 458712 en tratamiento", "historia_clinica"),
        ("nº de historia clínica: HC-2938471", "historia_clinica"),
        ("Tarjeta sanitaria AN1234567890", "tarjeta_sanitaria"),
        ("Nació el 12/03/1938 y toma digoxina", "fecha_nacimiento"),
        ("Residente Carmen Fernández López toma lorazepam", "nombre"),
        ("Juan García López, 87 años, ¿puede tomar atenolol?", "nombre"),
        ("Se llama Pilar y toma sertralina", "nombre"),
    ],
)
def test_detecta_cada_tipo(texto, tipo):
    r = check_pii(texto)
    assert r.contiene_pii
    assert tipo in r.tipos
    assert MASCARA in r.texto_enmascarado


def test_enmascara_solo_el_dato_y_conserva_la_pregunta():
    r = check_pii("Paciente con NHC 458712: ¿interacciona Aldocumar con ibuprofeno?")
    assert "458712" not in r.texto_enmascarado
    assert "NHC" in r.texto_enmascarado
    assert "¿interacciona Aldocumar con ibuprofeno?" in r.texto_enmascarado


def test_varios_datos_en_una_pregunta():
    r = check_pii(
        "Residente Ana Ruiz Pérez (NHC 458712), teléfono 612345678, DNI 12345678Z"
    )
    assert set(r.tipos) >= {"nombre", "historia_clinica", "telefono", "dni"}
    for dato in ["Ana Ruiz", "458712", "612345678", "12345678Z"]:
        assert dato not in r.texto_enmascarado


@pytest.mark.parametrize(
    "texto",
    [
        "¿Se puede triturar el atenolol de 100 mg?",
        "¿Cuál es la dosis de amoxicilina de 1000 mg cada 8 horas?",
        "¿Qué dice la sección 4.5 sobre interacciones?",
        "¿Interacciona la sertralina con el omeprazol?",
        "Registro 63062 de Aldocumar 1 mg comprimidos",
        "nregistro 114944012, Abasaglar 100 unidades/ml",
        "¿Cuánto dura Eliquis 2,5 mg una vez abierto?",
        "Paciente de 87 años con insuficiencia renal: ¿ajuste de dosis?",
        "¿Es compatible con la lactancia?",
    ],
)
def test_sin_falsos_positivos_en_preguntas_normales(texto):
    r = check_pii(texto)
    assert not r.contiene_pii
    assert r.tipos == []
    assert r.texto_enmascarado == texto


def test_texto_vacio():
    r = check_pii("")
    assert not r.contiene_pii
    assert r.texto_enmascarado == ""


def test_se_puede_desactivar_por_entorno(monkeypatch):
    monkeypatch.setenv("PII_FILTER_ENABLED", "false")
    texto = "Mi DNI es 12345678Z"
    r = check_pii(texto)
    assert not r.contiene_pii
    assert r.texto_enmascarado == texto


def test_resultado_cumple_el_contrato():
    r = check_pii("DNI 12345678Z")
    assert isinstance(r.contiene_pii, bool)
    assert isinstance(r.tipos, list)
    assert isinstance(r.texto_enmascarado, str)


@pytest.mark.parametrize(
    "texto, tipo_esperado, tipo_no_esperado",
    [
        ("DNI 12345678Z", "dni", "dni_posible"),  # letra correcta
        ("DNI 12345678A", "dni_posible", "dni"),  # letra incorrecta
        ("NIE X1234567L", "nie", "nie_posible"),  # letra correcta
        ("NIE X1234567A", "nie_posible", "nie"),  # letra incorrecta
        ("NIE y1234567z", "nie_posible", "nie"),  # minúsculas, letra incorrecta
    ],
)
def test_la_letra_de_control_decide_el_tipo(texto, tipo_esperado, tipo_no_esperado):
    r = check_pii(texto)
    assert tipo_esperado in r.tipos
    assert tipo_no_esperado not in r.tipos


@pytest.mark.parametrize("texto", ["DNI 12345678A", "NIE X1234567A", "NIE X1234567-A"])
def test_un_documento_con_letra_incorrecta_se_enmascara_igualmente(texto):
    r = check_pii(texto)
    assert r.contiene_pii
    assert "1234567" not in r.texto_enmascarado
    assert MASCARA in r.texto_enmascarado
