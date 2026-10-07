"""Tests del catálogo sin conexión (cliente de CIMA falso).

Responsable: P1
"""
from pathlib import Path

from src.ingestion.catalogo import (
    construir_catalogo,
    elegir_candidato,
    leer_catalogo,
    leer_lista,
)
from src.ingestion.cima_client import CimaClient, CimaError


def med(nregistro, secc=True, con_ficha=True, pactivos="X"):
    """El resultado tal y como lo devuelve la BÚSQUEDA de CIMA: sin 'pactivos' de verdad
    (ese campo solo está en el detalle), aunque aquí lo guardamos para que ClienteFalso
    pueda simular lo que devolvería cliente.obtener() para ese nregistro."""
    docs = [{"tipo": 2, "url": "p.pdf"}]
    if con_ficha:
        docs.append({"tipo": 1, "url": f"https://x/FT_{nregistro}.pdf", "secc": secc})
    return {"nregistro": nregistro, "nombre": f"MED {nregistro}", "pactivos": pactivos,
            "atcs": [{"codigo": "A01", "nivel": 3}], "docs": docs}


class ClienteFalso:
    """busquedas[pa] puede ser una lista (solo hay página 1) o un dict {pagina: [...]}
    para simular resultados repartidos en varias páginas.

    Los medicamentos que aparecen en cualquier búsqueda quedan registrados por nregistro,
    así que obtener(nregistro) devuelve su detalle real (con su pactivos), igual que CIMA:
    la búsqueda no trae el principio activo, pero el detalle sí."""

    def __init__(self, busquedas: dict, errores=(), medicamentos=()):
        self.busquedas, self.errores, self.llamadas = busquedas, set(errores), []
        self._medicamentos = {}
        for resultado in busquedas.values():
            paginas = resultado.values() if isinstance(resultado, dict) else [resultado]
            for pagina in paginas:
                for r in pagina:
                    self._medicamentos[str(r["nregistro"])] = r
        for r in medicamentos:  # candidatos que no vienen de una búsqueda (tests de elegir_candidato)
            self._medicamentos[str(r["nregistro"])] = r

    def buscar(self, principio_activo, un_solo_principio_activo, pagina=1):
        self.llamadas.append(principio_activo)
        assert un_solo_principio_activo is True
        if principio_activo in self.errores:
            raise CimaError("caída")
        resultado = self.busquedas.get(principio_activo, [])
        if isinstance(resultado, dict):
            return resultado.get(pagina, [])
        return resultado if pagina == 1 else []

    def obtener(self, nregistro):
        return CimaClient.a_info(self._medicamentos[str(nregistro)])


def test_leer_lista_ignora_comentarios_vacias_y_duplicados(tmp_path: Path):
    f = tmp_path / "pa.txt"
    f.write_text("# grupo\nparacetamol\n\nOmeprazol\nomeprazol\n", encoding="utf-8")
    assert leer_lista(f) == ["paracetamol", "Omeprazol"]


def test_elegir_prefiere_ficha_segmentada():
    candidatos = [med("1", secc=False, pactivos="x"), med("2", secc=True, pactivos="x")]
    cliente = ClienteFalso({}, medicamentos=candidatos)
    assert elegir_candidato(cliente, candidatos, "x").nregistro == "2"


def test_elegir_descarta_sin_ficha_tecnica():
    candidatos = [med("1", con_ficha=False, pactivos="x"), med("2", secc=False, pactivos="x")]
    cliente = ClienteFalso({}, medicamentos=candidatos)
    assert elegir_candidato(cliente, candidatos[:1], "x") is None
    assert elegir_candidato(cliente, candidatos, "x").nregistro == "2"


def test_elegir_descarta_principio_activo_que_solo_contiene_la_subcadena():
    # CIMA (practiv1) devuelve por subcadena: buscar "ibuprofeno" también trae "DEXIBUPROFENO".
    # No es el mismo principio activo (y la búsqueda no lo dice: hay que mirar el detalle).
    candidatos = [med("1", pactivos="DEXIBUPROFENO")]
    cliente = ClienteFalso({}, medicamentos=candidatos)
    assert elegir_candidato(cliente, candidatos, "ibuprofeno") is None


def test_elegir_acepta_variante_de_sal():
    # "naproxeno" -> "NAPROXENO SODICO" sí es una coincidencia válida (misma molécula).
    candidatos = [med("1", pactivos="NAPROXENO SODICO")]
    cliente = ClienteFalso({}, medicamentos=candidatos)
    assert elegir_candidato(cliente, candidatos, "naproxeno").nregistro == "1"


def test_elegir_acepta_forma_acido_en_cualquier_orden():
    # "acetilsalicilico" -> "ACIDO ACETILSALICILICO": la palabra buscada está, aunque no
    # vaya la primera. Comparamos por palabras, no por prefijo.
    candidatos = [med("1", pactivos="ACIDO ACETILSALICILICO")]
    cliente = ClienteFalso({}, medicamentos=candidatos)
    assert elegir_candidato(cliente, candidatos, "acetilsalicilico").nregistro == "1"


def test_elegir_prefiere_el_de_principio_activo_exacto():
    # Si hay varios candidatos, el que tiene el principio activo exacto gana aunque el otro
    # tenga ficha segmentada y el exacto no.
    candidatos = [med("1", pactivos="DEXIBUPROFENO", secc=True), med("2", pactivos="IBUPROFENO", secc=False)]
    cliente = ClienteFalso({}, medicamentos=candidatos)
    assert elegir_candidato(cliente, candidatos, "ibuprofeno").nregistro == "2"


def test_elegir_sigue_probando_candidatos_hasta_encontrar_el_exacto():
    # La búsqueda de CIMA no trae el principio activo: hay que ir pidiendo el detalle
    # candidato a candidato. Aquí el primero (y el único con ficha segmentada) es el
    # equivocado; el bueno es el segundo, sin ficha segmentada.
    candidatos = [med("1", pactivos="APOMORFINA", secc=True), med("2", pactivos="MORFINA", secc=False)]
    cliente = ClienteFalso({}, medicamentos=candidatos)
    assert elegir_candidato(cliente, candidatos, "morfina").nregistro == "2"


def test_construir_busca_en_varias_paginas_si_hiciera_falta(tmp_path: Path):
    csv = tmp_path / "catalogo.csv"
    cliente = ClienteFalso({
        "ibuprofeno": {1: [med("1", pactivos="DEXIBUPROFENO")], 2: [med("2", pactivos="IBUPROFENO")]},
    })
    r = construir_catalogo(["ibuprofeno"], cliente, csv)
    assert r["añadidos"] == 1
    assert leer_catalogo(csv)[0]["nregistro"] == "2"


def test_construir_catalogo_y_resumen(tmp_path: Path):
    csv = tmp_path / "catalogo.csv"
    # mismo nregistro alcanzado por dos búsquedas distintas (p. ej. un medicamento con dos
    # principios activos, "A, B"): debe deduplicarse por nregistro, no repetirse en el catálogo.
    med_ab = med("1", pactivos="A, B")
    cliente = ClienteFalso({"a": [med_ab], "b": [med_ab], "c": []}, errores={"d"})
    r = construir_catalogo(["a", "b", "c", "d"], cliente, csv)
    assert r["añadidos"] == 1
    assert r["ya_estaban"] == 1          # "b" lleva al mismo medicamento que "a"
    assert r["sin_resultado"] == ["c"]
    assert r["errores"] == ["d"]
    filas = leer_catalogo(csv)
    assert filas[0]["nregistro"] == "1" and filas[0]["atc"] == "A01"


def test_es_reanudable(tmp_path: Path):
    csv = tmp_path / "catalogo.csv"
    construir_catalogo(["a"], ClienteFalso({"a": [med("1", pactivos="a")]}), csv)
    cliente = ClienteFalso({"a": [med("1", pactivos="a")], "b": [med("2", pactivos="b")]})
    construir_catalogo(["a", "b"], cliente, csv)
    assert set(cliente.llamadas) == {"b"}     # "a" no se vuelve a buscar (solo se pide "b", pagine lo que pagine)
    assert [f["nregistro"] for f in leer_catalogo(csv)] == ["1", "2"]


def test_catalogo_con_formato_antiguo_da_error_claro(tmp_path: Path):
    import pytest
    csv = tmp_path / "catalogo.csv"
    csv.write_text("nregistro,nombre,principio_activo,atc\n# comentario\n", encoding="utf-8")
    with pytest.raises(ValueError, match="formato antiguo"):
        leer_catalogo(csv)
