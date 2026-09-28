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


def med(nregistro, secc=True, con_ficha=True):
    docs = [{"tipo": 2, "url": "p.pdf"}]
    if con_ficha:
        docs.append({"tipo": 1, "url": f"https://x/FT_{nregistro}.pdf", "secc": secc})
    return {"nregistro": nregistro, "nombre": f"MED {nregistro}", "pactivos": "X",
            "atcs": [{"codigo": "A01", "nivel": 3}], "docs": docs}


class ClienteFalso:
    def __init__(self, busquedas: dict, errores=()):
        self.busquedas, self.errores, self.llamadas = busquedas, set(errores), []

    def buscar(self, principio_activo, un_solo_principio_activo):
        self.llamadas.append(principio_activo)
        assert un_solo_principio_activo is True
        if principio_activo in self.errores:
            raise CimaError("caída")
        return self.busquedas.get(principio_activo, [])

    def obtener(self, nregistro):
        return CimaClient.a_info(med(nregistro))


def test_leer_lista_ignora_comentarios_vacias_y_duplicados(tmp_path: Path):
    f = tmp_path / "pa.txt"
    f.write_text("# grupo\nparacetamol\n\nOmeprazol\nomeprazol\n", encoding="utf-8")
    assert leer_lista(f) == ["paracetamol", "Omeprazol"]


def test_elegir_prefiere_ficha_segmentada():
    assert elegir_candidato([med("1", secc=False), med("2", secc=True)])["nregistro"] == "2"


def test_elegir_descarta_sin_ficha_tecnica():
    assert elegir_candidato([med("1", con_ficha=False)]) is None
    assert elegir_candidato([med("1", con_ficha=False), med("2", secc=False)])["nregistro"] == "2"


def test_construir_catalogo_y_resumen(tmp_path: Path):
    csv = tmp_path / "catalogo.csv"
    cliente = ClienteFalso({"a": [med("1")], "b": [med("1")], "c": []}, errores={"d"})
    r = construir_catalogo(["a", "b", "c", "d"], cliente, csv)
    assert r["añadidos"] == 1
    assert r["ya_estaban"] == 1          # "b" lleva al mismo medicamento que "a"
    assert r["sin_resultado"] == ["c"]
    assert r["errores"] == ["d"]
    filas = leer_catalogo(csv)
    assert filas[0]["nregistro"] == "1" and filas[0]["atc"] == "A01"


def test_es_reanudable(tmp_path: Path):
    csv = tmp_path / "catalogo.csv"
    construir_catalogo(["a"], ClienteFalso({"a": [med("1")]}), csv)
    cliente = ClienteFalso({"a": [med("1")], "b": [med("2")]})
    construir_catalogo(["a", "b"], cliente, csv)
    assert cliente.llamadas == ["b"]     # "a" no se vuelve a buscar
    assert [f["nregistro"] for f in leer_catalogo(csv)] == ["1", "2"]


def test_catalogo_con_formato_antiguo_da_error_claro(tmp_path: Path):
    import pytest
    csv = tmp_path / "catalogo.csv"
    csv.write_text("nregistro,nombre,principio_activo,atc\n# comentario\n", encoding="utf-8")
    with pytest.raises(ValueError, match="formato antiguo"):
        leer_catalogo(csv)
