"""Tests del cliente de CIMA sin conexión a internet (la sesión HTTP es falsa).

Responsable: P1
"""
from pathlib import Path

import pytest
import requests

from src.ingestion.cima_client import CimaClient, CimaError

MEDICAMENTO = {
    "nregistro": "51347",
    "nombre": "EJEMPLO 1 g COMPRIMIDOS",
    "pactivos": "PARACETAMOL",
    "atcs": [{"codigo": "N02B", "nivel": 4}, {"codigo": "N02BE01", "nivel": 5}],
    "docs": [
        {"tipo": 2, "url": "https://cima.aemps.es/cima/pdfs/p/51347/P_51347.pdf", "secc": True},
        {"tipo": 1, "url": "https://cima.aemps.es/cima/pdfs/ft/51347/FT_51347.pdf", "secc": True},
    ],
}


class RespuestaFalsa:
    def __init__(self, status=200, json_data=None, content=b""):
        self.status_code = status
        self._json = json_data
        self.content = content if json_data is None else b"{...}"

    def json(self):
        return self._json


class SesionFalsa:
    """Devuelve las respuestas en orden y guarda las llamadas."""

    def __init__(self, respuestas):
        self.respuestas = list(respuestas)
        self.llamadas = []
        self.headers = {}

    def get(self, url, params=None, timeout=None):
        self.llamadas.append((url, params))
        r = self.respuestas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


@pytest.fixture(autouse=True)
def sin_esperas(monkeypatch):
    monkeypatch.setattr("src.ingestion.cima_client.time.sleep", lambda s: None)


def cliente(respuestas):
    return CimaClient(pausa=0, session=SesionFalsa(respuestas))


def test_a_info_elige_ficha_tecnica_y_atc_mas_especifico():
    info = CimaClient.a_info(MEDICAMENTO)
    assert info.url_ficha_tecnica.endswith("FT_51347.pdf")
    assert info.atc == "N02BE01"
    assert info.ficha_segmentada is True


def test_buscar_devuelve_resultados_y_manda_filtros():
    c = cliente([RespuestaFalsa(json_data={"resultados": [MEDICAMENTO]})])
    res = c.buscar(principio_activo="paracetamol")
    assert res[0]["nregistro"] == "51347"
    _, params = c.session.llamadas[0]
    assert params["practiv1"] == "paracetamol" and params["comerc"] == 1


def test_buscar_sin_criterios_da_error():
    with pytest.raises(ValueError):
        cliente([]).buscar()


def test_obtener_inexistente_lanza_cima_error():
    with pytest.raises(CimaError):
        cliente([RespuestaFalsa(status=204)]).obtener("000")


def test_reintenta_tras_error_de_red():
    c = cliente([requests.ConnectionError("caída"), RespuestaFalsa(json_data=MEDICAMENTO)])
    assert c.obtener("51347").nregistro == "51347"
    assert len(c.session.llamadas) == 2


def test_se_rinde_tras_agotar_reintentos():
    c = cliente([RespuestaFalsa(status=503)] * 3)
    with pytest.raises(CimaError):
        c.obtener("51347")


def test_descarga_pdf(tmp_path: Path):
    info = CimaClient.a_info(MEDICAMENTO)
    ruta = cliente([RespuestaFalsa(content=b"%PDF-1.7 contenido")]).descargar_ficha_tecnica(info, tmp_path)
    assert ruta.name == "FT_51347.pdf" and ruta.read_bytes().startswith(b"%PDF")


def test_rechaza_descarga_que_no_es_pdf(tmp_path: Path):
    info = CimaClient.a_info(MEDICAMENTO)
    with pytest.raises(CimaError):
        cliente([RespuestaFalsa(content=b"<html>error</html>")]).descargar_ficha_tecnica(info, tmp_path)
    assert not list(tmp_path.iterdir())


def test_no_vuelve_a_descargar_si_ya_existe(tmp_path: Path):
    (tmp_path / "FT_51347.pdf").write_bytes(b"%PDF previo")
    c = cliente([])
    c.descargar_ficha_tecnica(CimaClient.a_info(MEDICAMENTO), tmp_path)
    assert c.session.llamadas == []
