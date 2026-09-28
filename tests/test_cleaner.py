"""Tests de la limpieza de texto.

Responsable: P1
"""
from pathlib import Path

from src.ingestion.cleaner import (
    limpiar_documento,
    limpiar_texto,
    quitar_lineas_repetidas,
    quitar_numeros_de_pagina,
)
from src.ingestion.loaders import Pagina, cargar_documento

FIXTURES = Path(__file__).parent / "fixtures"


def test_caracteres_raros_de_pdf():
    t = limpiar_texto("dosis\u00a0diaria de para\u00adcetamol, \ufb01ltrar\n\uf0b7 \nCefalea")
    assert t == "dosis diaria de paracetamol, filtrar\n• Cefalea"


def test_quita_numeros_de_pagina_pero_no_titulos():
    paginas = [Pagina(1, "1 de 5\nFICHA TÉCNICA\n4.\nDATOS CLÍNICOS\ntexto\n29")]
    texto = quitar_numeros_de_pagina(paginas)[0].texto
    assert "1 de 5" not in texto and "29" not in texto
    assert "4." in texto


def test_une_titulo_ema_partido():
    assert limpiar_texto("4.2 \n\nPosología y forma de administración\nTexto.") == (
        "4.2 Posología y forma de administración\nTexto.")


def test_une_vinetas_partidas():
    assert limpiar_texto("- \nPrimera indicación.\n• \nSegunda.") == "- Primera indicación.\n• Segunda."


def test_une_guion_de_fin_de_linea_solo_entre_letras():
    assert limpiar_texto("se une exten-\nsamente a proteínas") == "se une extensamente a proteínas"
    assert "1-\n10 microgramos" in limpiar_texto("entre 1-\n10 microgramos")  # rangos numéricos intactos


def test_une_lineas_de_un_mismo_parrafo():
    t = limpiar_texto("El tratamiento debe iniciarse a dosis\nbajas e ir incrementando.\nPoblación pediátrica")
    assert t == "El tratamiento debe iniciarse a dosis bajas e ir incrementando.\nPoblación pediátrica"


def test_no_mete_el_texto_de_la_seccion_en_el_titulo():
    t = limpiar_texto("10. FECHA DE LA REVISIÓN DEL TEXTO\nnoviembre 2023")
    assert t == "10. FECHA DE LA REVISIÓN DEL TEXTO\nnoviembre 2023"
    t = limpiar_texto("9. FECHA DE LA PRIMERA AUTORIZACIÓN/RENOVACIÓN DE LA\nAUTORIZACIÓN")
    assert t == "9. FECHA DE LA PRIMERA AUTORIZACIÓN/RENOVACIÓN DE LA AUTORIZACIÓN"


def test_quita_cabeceras_repetidas():
    paginas = [Pagina(i, f"Guía de farmacia · Hospital X\ncontenido {i}") for i in range(1, 6)]
    assert all("Guía de farmacia" not in p.texto for p in quitar_lineas_repetidas(paginas))


def test_fila_de_tabla_sin_valores():
    assert limpiar_texto("Dosis alternativa —") == "Dosis alternativa"


def test_ficha_real_conserva_paginas_y_secciones():
    doc = limpiar_documento(cargar_documento(FIXTURES / "FT_11265.pdf"))
    assert [p.numero for p in doc.paginas] == [1, 2, 3, 4, 5]
    texto = doc.texto_completo
    assert "5 de 5" not in texto
    assert "4.5. Interacción con otros medicamentos y otras formas de interacción" in texto.splitlines()
    assert "\n\n\n" not in texto


def test_une_lineas_que_empiezan_por_numero_si_la_anterior_llega_al_margen():
    larga = "Si es necesario suspender el tratamiento antes de la cirugía, debe hacerse gradualmente y finalizarse unas"
    assert limpiar_texto(f"{larga}\n48 horas antes.") == f"{larga} 48 horas antes."
    # Una línea corta seguida de una nota numerada no se une
    assert limpiar_texto("Fatiga\n1 a dosis superiores") == "Fatiga\n1 a dosis superiores"
    # Nunca se pega un título de sección
    assert limpiar_texto(f"{larga}\n4.3. Contraindicaciones") == f"{larga}\n4.3. Contraindicaciones"


def test_coma_al_principio_de_linea():
    assert limpiar_texto("muy frecuentes (≥1/10)\n, frecuentes") == "muy frecuentes (≥1/10), frecuentes"


def test_espacio_antes_del_punto_en_titulo():
    assert limpiar_texto("6 . DATOS FARMACÉUTICOS") == "6. DATOS FARMACÉUTICOS"


def test_no_une_filas_de_tabla():
    t = "Dosis prescrita — Semana 1: 1 mg/kg\n10 kg — Semana 1: 1 ml"
    assert limpiar_texto(t) == t
