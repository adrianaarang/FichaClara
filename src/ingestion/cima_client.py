"""Cliente de la API REST de CIMA (AEMPS).

Busca medicamentos, obtiene sus datos y descarga el PDF de la ficha técnica.
Documentación oficial: https://sede.aemps.gob.es/docs/CIMA-REST-API_1_19.pdf

Responsable: P1 · Ingesta y chunking
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path

import requests

BASE_URL = "https://cima.aemps.es/cima/rest"
TIPO_FICHA_TECNICA = 1
TIPO_PROSPECTO = 2

logger = logging.getLogger(__name__)


class CimaError(Exception):
    """Error al consultar CIMA o al descargar un documento."""


@dataclass
class MedicamentoInfo:
    """Datos de un medicamento que necesitamos para la ingesta y los metadatos."""

    nregistro: str
    nombre: str
    principios_activos: str
    atc: str | None
    url_ficha_tecnica: str | None
    ficha_segmentada: bool  # True si CIMA la tiene también dividida por secciones

    @property
    def url_ficha_html(self) -> str:
        """Enlace a la ficha en CIMA (para mostrarlo como fuente en el frontend)."""
        return f"https://cima.aemps.es/cima/dochtml/ft/{self.nregistro}/FichaTecnica.html"


class CimaClient:
    """Cliente sencillo con pausa entre peticiones y reintentos.

    Ejemplo:
        cliente = CimaClient()
        info = cliente.obtener("51347")
        ruta = cliente.descargar_ficha_tecnica(info, Path("data/raw"))
    """

    def __init__(
        self,
        pausa: float = 0.5,
        reintentos: int = 3,
        timeout: float = 30,
        session: requests.Session | None = None,
    ) -> None:
        self.pausa = pausa  # segundos mínimos entre peticiones (no saturar a la AEMPS)
        self.reintentos = reintentos
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": "FichaClara/0.1 (proyecto educativo)"})
        self._ultima_peticion = 0.0

    # ------------------------------------------------------------------ internos

    def _esperar_turno(self) -> None:
        transcurrido = time.monotonic() - self._ultima_peticion
        if transcurrido < self.pausa:
            time.sleep(self.pausa - transcurrido)
        self._ultima_peticion = time.monotonic()

    def _peticion(self, url: str, params: dict | None = None) -> requests.Response:
        """GET con reintentos ante errores de red o errores 5xx del servidor."""
        ultimo_error: Exception | None = None
        for intento in range(1, self.reintentos + 1):
            self._esperar_turno()
            try:
                resp = self.session.get(url, params=params, timeout=self.timeout)
            except (requests.ConnectionError, requests.Timeout) as e:
                ultimo_error = e
                logger.warning("Error de red en %s (intento %d/%d): %s", url, intento, self.reintentos, e)
            else:
                if resp.status_code < 500:
                    return resp
                ultimo_error = CimaError(f"HTTP {resp.status_code}")
                logger.warning("CIMA devolvió %d en %s (intento %d/%d)", resp.status_code, url, intento, self.reintentos)
            time.sleep(2 ** intento)  # espera creciente: 2 s, 4 s, 8 s...
        raise CimaError(f"No se pudo acceder a {url} tras {self.reintentos} intentos: {ultimo_error}")

    def _get_json(self, recurso: str, params: dict | None = None) -> dict | list:
        resp = self._peticion(f"{BASE_URL}/{recurso}", params)
        if resp.status_code == 204 or not resp.content:
            return {}  # CIMA responde vacío cuando no encuentra nada
        if resp.status_code >= 400:
            raise CimaError(f"HTTP {resp.status_code} en {recurso} con {params}")
        return resp.json()

    # ------------------------------------------------------------------ públicos

    def buscar(self, nombre: str | None = None, principio_activo: str | None = None,
               solo_comercializados: bool = True, un_solo_principio_activo: bool = False,
               pagina: int = 1) -> list[dict]:
        """Busca medicamentos autorizados por nombre o principio activo.

        Devuelve la lista 'resultados' de CIMA tal cual (dicts con nregistro, nombre, docs...).
        Con un_solo_principio_activo=True descarta las combinaciones (p. ej. paracetamol + cafeína).
        """
        if not nombre and not principio_activo:
            raise ValueError("Indica un nombre o un principio activo")
        params: dict = {"autorizados": 1, "pagina": pagina}
        if nombre:
            params["nombre"] = nombre
        if principio_activo:
            params["practiv1"] = principio_activo
        if solo_comercializados:
            params["comerc"] = 1
        if un_solo_principio_activo:
            params["npactiv"] = 1
        datos = self._get_json("medicamentos", params)
        return datos.get("resultados", []) if isinstance(datos, dict) else []

    def obtener(self, nregistro: str) -> MedicamentoInfo:
        """Detalle de un medicamento por su número de registro."""
        datos = self._get_json("medicamento", {"nregistro": nregistro})
        if not datos:
            raise CimaError(f"No existe ningún medicamento con nº de registro {nregistro}")
        return self.a_info(datos)

    @staticmethod
    def a_info(datos: dict) -> MedicamentoInfo:
        """Convierte el JSON de CIMA en nuestro MedicamentoInfo."""
        ficha = next((d for d in datos.get("docs") or [] if d.get("tipo") == TIPO_FICHA_TECNICA), None)
        atcs = datos.get("atcs") or []
        # Nos quedamos con el ATC más específico (el de mayor nivel)
        atc = max(atcs, key=lambda a: a.get("nivel", 0)).get("codigo") if atcs else None
        return MedicamentoInfo(
            nregistro=str(datos["nregistro"]),
            nombre=datos.get("nombre", ""),
            principios_activos=datos.get("pactivos", ""),
            atc=atc,
            url_ficha_tecnica=ficha.get("url") if ficha else None,
            ficha_segmentada=bool(ficha.get("secc")) if ficha else False,
        )

    def descargar_ficha_tecnica(self, info: MedicamentoInfo, carpeta: Path,
                                sobrescribir: bool = False) -> Path:
        """Descarga el PDF de la ficha técnica en carpeta/FT_<nregistro>.pdf."""
        if not info.url_ficha_tecnica:
            raise CimaError(f"{info.nombre} ({info.nregistro}) no tiene ficha técnica publicada")
        carpeta.mkdir(parents=True, exist_ok=True)
        destino = carpeta / f"FT_{info.nregistro}.pdf"
        if destino.exists() and not sobrescribir:
            logger.info("Ya descargada: %s", destino.name)
            return destino

        resp = self._peticion(info.url_ficha_tecnica)
        if resp.status_code >= 400:
            raise CimaError(f"HTTP {resp.status_code} al descargar {info.url_ficha_tecnica}")
        if not resp.content.startswith(b"%PDF"):
            raise CimaError(f"La ficha de {info.nregistro} no es un PDF (¿solo existe en HTML?)")

        temporal = destino.with_suffix(".part")  # si se corta la descarga no queda un PDF roto
        temporal.write_bytes(resp.content)
        temporal.replace(destino)
        logger.info("Descargada: %s (%d KB)", destino.name, len(resp.content) // 1024)
        return destino

    def principios_activos(self, max_paginas: int = 100) -> list[str]:
        """Todos los principios activos de la maestra de CIMA (maestra=1), paginando."""
        nombres: list[str] = []
        for pagina in range(1, max_paginas + 1):
            datos = self._get_json("maestras", {"maestra": 1, "pagina": pagina})
            resultados = datos.get("resultados", []) if isinstance(datos, dict) else datos or []
            if not resultados:
                break
            nombres += [r["nombre"] for r in resultados if r.get("nombre")]
            total = datos.get("totalFilas") if isinstance(datos, dict) else None
            if total is not None and len(nombres) >= total:
                break
        return nombres

    def secciones_oficiales(self, nregistro: str) -> list[dict]:
        """Lista de secciones de la ficha según CIMA (sin contenido).

        Sirve para validar que nuestro chunker detecta bien las secciones.
        Cada elemento tiene: seccion ('4.2'), titulo y orden.
        """
        datos = self._get_json(f"docSegmentado/secciones/{TIPO_FICHA_TECNICA}", {"nregistro": nregistro})
        return datos if isinstance(datos, list) else []


if __name__ == "__main__":
    # Prueba rápida:  python -m src.ingestion.cima_client
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cliente = CimaClient()

    resultados = cliente.buscar(principio_activo="paracetamol")
    print(f"Encontrados {len(resultados)} medicamentos con paracetamol. Primeros 3:")
    for r in resultados[:3]:
        print(f"  {r['nregistro']}  {r['nombre']}")

    info = cliente.obtener(resultados[0]["nregistro"])
    print(f"\n{info}\n")

    ruta = cliente.descargar_ficha_tecnica(info, Path("data/raw"))
    print(f"PDF guardado en {ruta}")

    secciones = cliente.secciones_oficiales(info.nregistro)
    print(f"\nSecciones oficiales ({len(secciones)}):")
    for s in secciones[:12]:
        print(f"  {s.get('seccion'):>5}  {s.get('titulo')}")
