"""Chunking de documentos: por sección de ficha técnica + troceo recursivo dentro de las largas.

Estrategia (justificación completa en docs/chunking.md):

1. Las fichas técnicas siguen una plantilla oficial con secciones numeradas
   (4.2 Posología, 4.5 Interacciones, 4.8 Reacciones adversas...). Cada sección responde
   a un tipo de pregunta, así que la sección es la unidad natural del chunk.
2. Solo se aceptan como títulos los números de la plantilla oficial, en orden y con un
   título que encaje. Así no confundimos "(ver sección 4.3)" ni una lista "1. Poner..."
   con un título.
3. Si una sección cabe en MAX_SECCION caracteres → 1 chunk.
   Si no → subtrozos de TAM_CHUNK con SOLAPE de solapamiento, SOLO dentro de la sección
   (nunca mezcla 4.5 con 4.6).
4. Cada chunk empieza con una cabecera de contexto: "[Lopresor 100 mg · 4.5 Interacción...]".
   Un subtrozo suelto de 4.8 no dice de qué fármaco habla; la cabecera sí.
5. Documentos que no son fichas técnicas (guías subidas) → troceo recursivo genérico,
   respetando los títulos Markdown si los hay.

Responsable: P1 · Ingesta y chunking
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.common.schemas import Chunk, ChunkMetadata
from src.ingestion.loaders import DocumentoCargado

logger = logging.getLogger(__name__)

MAX_SECCION = 1500   # caracteres: una sección hasta este tamaño va entera en un chunk
TAM_CHUNK = 1000     # tamaño de los subtrozos de las secciones largas
SOLAPE = 150         # ~15 %: evita cortar una frase o una fila de tabla entre dos chunks
MIN_SECCIONES = 8    # si detectamos menos, el PDF es raro: usamos el troceo genérico

# Plantilla oficial de la ficha técnica (RCP). Clave: número de sección.
# Valor: palabras (sin tildes, en minúscula) que deben aparecer en su título.
PLANTILLA: dict[str, tuple[str, ...]] = {
    "1": ("nombre",), "2": ("composicion",), "3": ("forma farmaceutica",), "4": ("datos clinicos",),
    "4.1": ("indicacion",), "4.2": ("posologia",), "4.3": ("contraindicacion",),
    "4.4": ("advertencia", "precaucion"), "4.5": ("interaccion",), "4.6": ("embarazo", "fertilidad", "lactancia"),
    "4.7": ("conducir", "maquinas"), "4.8": ("reacciones adversas",), "4.9": ("sobredosis",),
    "5": ("propiedades farmacologicas",), "5.1": ("farmacodinamic",), "5.2": ("farmacocinetic",),
    "5.3": ("preclinic",),
    "6": ("datos farmaceuticos",), "6.1": ("excipiente",), "6.2": ("incompatibilidad",), "6.3": ("validez",),
    "6.4": ("conservacion",), "6.5": ("envase",), "6.6": ("eliminacion", "manipulacion"),
    "7": ("titular",), "8": ("autorizacion",), "9": ("primera autorizacion", "renovacion"),
    "10": ("revision",), "11": ("dosimetria",), "12": ("instrucciones", "radiofarmaco"),
}
ORDEN_PLANTILLA = list(PLANTILLA)

RE_TITULO = re.compile(r"^(\d{1,2}(?:\.\d{1,2})?)\.?\s+(\S.*)$")
RE_MARKDOWN = re.compile(r"^#{1,6}\s+(.+)$")
URL_CIMA_SECCION = "https://cima.aemps.es/cima/dochtml/ft/{nregistro}/{seccion}/FichaTecnica.html"
URL_CIMA_FICHA = "https://cima.aemps.es/cima/dochtml/ft/{nregistro}/FichaTecnica.html"


@dataclass
class Seccion:
    numero: str | None
    titulo: str | None
    texto: str
    paginas: list[int]  # página de cada carácter no hace falta: guardamos (inicio_linea → página)
    offsets: list[tuple[int, int]]  # (offset en texto, página) al comienzo de cada línea
    producto: int = 1  # algunas fichas EMA traen varias presentaciones seguidas (1..10, 1..10…)


# ---------------------------------------------------------------- entrada principal

def trocear_documento(doc: DocumentoCargado, info: dict | None = None, *,
                      max_seccion: int = MAX_SECCION, tam_chunk: int = TAM_CHUNK,
                      solape: int = SOLAPE) -> list[Chunk]:
    """Convierte un documento (ya limpio) en chunks con metadatos.

    info: fila del catálogo (nombre, principios_activos, atc) si es una ficha técnica.
    """
    info = info or {}
    secciones = detectar_secciones(doc) if doc.es_ficha_tecnica else []
    if doc.es_ficha_tecnica and len(secciones) < MIN_SECCIONES:
        logger.warning("%s: solo %d secciones reconocidas, uso el troceo genérico", doc.doc_id, len(secciones))
        secciones = []
    es_ficha = bool(secciones)
    if not es_ficha:
        secciones = secciones_genericas(doc)

    # Nombre y fecha por producto: en una ficha EMA con varias presentaciones, cada bloque 1..10
    # tiene su propio nombre (sección 1) y su fecha (sección 10).
    nombres, fechas = {}, {}
    for s in secciones:
        if s.numero == "1" and s.texto:
            nombres[s.producto] = s.texto.split("\n")[0].strip()
        if s.numero == "10":
            fechas[s.producto] = extraer_fecha(s.texto)
    nombre_doc = info.get("nombre") or doc.ruta.name
    fecha_doc = next((f for f in fechas.values() if f), None)

    divisor = RecursiveCharacterTextSplitter(chunk_size=tam_chunk, chunk_overlap=solape, add_start_index=True,
                                             separators=["\n\n", "\n", ". ", "; ", ", ", " ", ""])
    chunks: list[Chunk] = []
    for s in secciones:
        if len(s.texto) < 3:
            continue  # títulos sin contenido propio, p. ej. "4. DATOS CLÍNICOS" justo antes de 4.1
        if len(s.texto) <= max_seccion:
            trozos = [(0, s.texto)]
        else:
            trozos = [(d.metadata["start_index"], d.page_content) for d in divisor.create_documents([s.texto])]

        nombre = nombres.get(s.producto) or nombre_doc
        fecha = fechas.get(s.producto) or fecha_doc
        prefijo_id = f"{doc.doc_id}::" if s.producto == 1 else f"{doc.doc_id}::p{s.producto}::"
        for parte, (inicio, trozo) in enumerate(trozos, start=1):
            pag_ini = _pagina_en(s, inicio)
            pag_fin = _pagina_en(s, inicio + len(trozo) - 1)
            etiqueta = f"{s.numero} {s.titulo}" if s.numero else (s.titulo or "")
            cabecera = f"[{nombre}" + (f" · {etiqueta}" if etiqueta else "")
            cabecera += f" · parte {parte}/{len(trozos)}]" if len(trozos) > 1 else "]"
            metadata = ChunkMetadata(
                chunk_id=f"{prefijo_id}{s.numero or 'doc'}::{len(chunks) if not s.numero else parte}",
                doc_id=doc.doc_id,
                tipo_documento="ficha_tecnica" if es_ficha else "documento",
                nombre=nombre,
                nregistro=doc.nregistro,
                principios_activos=info.get("principios_activos") or None,
                atc=info.get("atc") or None,
                origen=doc.origen if es_ficha else None,
                fecha_revision=fecha,
                seccion=s.numero,
                titulo_seccion=s.titulo,
                pagina_inicio=pag_ini,
                pagina_fin=max(pag_ini, pag_fin),
                orden=len(chunks),
                parte=parte,
                total_partes=len(trozos),
                url_fuente=_url(doc, s.numero) if es_ficha else None,
            )
            chunks.append(Chunk(texto=f"{cabecera}\n{trozo.strip()}", metadata=metadata))
    return chunks


# ---------------------------------------------------------------- fichas técnicas

def _sin_tildes(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().lower()


def es_titulo_de_seccion(numero: str, titulo: str) -> bool:
    claves = PLANTILLA.get(numero)
    return bool(claves) and any(c in _sin_tildes(titulo) for c in claves)


def detectar_secciones(doc: DocumentoCargado) -> list[Seccion]:
    """Recorre las líneas y parte el documento por los títulos oficiales, en orden."""
    secciones: list[Seccion] = []
    actual: Seccion | None = None
    ultimo = -1  # posición en ORDEN_PLANTILLA del último título aceptado
    producto = 1
    fin_de_ficha = ORDEN_PLANTILLA.index("7")

    for pagina in doc.paginas:
        for linea in pagina.texto.split("\n"):
            m = RE_TITULO.match(linea.strip())
            if m:
                numero, titulo = m.group(1), m.group(2).strip()
                pos = ORDEN_PLANTILLA.index(numero) if numero in PLANTILLA else -1
                if numero == "1" and ultimo >= fin_de_ficha and es_titulo_de_seccion(numero, titulo):
                    producto += 1  # empieza la ficha de otra presentación dentro del mismo PDF (EMA)
                    ultimo = -1
                if pos > ultimo and es_titulo_de_seccion(numero, titulo):
                    actual = Seccion(numero, _titulo_bonito(titulo), "", [], [], producto)
                    secciones.append(actual)
                    ultimo = pos
                    continue
            if actual is None:
                continue  # "FICHA TÉCNICA" antes de la sección 1
            actual.offsets.append((len(actual.texto), pagina.numero))
            actual.texto += linea + "\n"
            if pagina.numero not in actual.paginas:
                actual.paginas.append(pagina.numero)
        # si una sección empieza al final de una página sin texto, que al menos tenga esa página
        if actual is not None and not actual.paginas:
            actual.paginas.append(pagina.numero)

    for s in secciones:
        s.texto = s.texto.strip("\n")
    return secciones


RE_FECHA = re.compile(
    r"\b(?:(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)"
    r"(?:\s+de)?\s+(?:19|20)\d{2}|\d{1,2}[/.-]\d{1,2}[/.-](?:19|20)\d{2}|\d{1,2}[/.-](?:19|20)\d{2})\b",
    re.IGNORECASE,
)


def extraer_fecha(texto: str) -> str | None:
    """Fecha de la sección 10 ('Julio 2024', '03/2023'...). None si no hay (p. ej. '<{MM/AAAA}>')."""
    m = RE_FECHA.search(texto)
    return m.group(0) if m else None


def _titulo_bonito(titulo: str) -> str:
    """'DATOS CLÍNICOS' → 'Datos clínicos'; 'Posología y forma...' se queda igual."""
    titulo = titulo.rstrip(" .")
    return titulo.capitalize() if titulo.isupper() else titulo


def _url(doc: DocumentoCargado, seccion: str | None) -> str | None:
    if not doc.nregistro:
        return None
    if seccion:
        return URL_CIMA_SECCION.format(nregistro=doc.nregistro, seccion=seccion)
    return URL_CIMA_FICHA.format(nregistro=doc.nregistro)


def _pagina_en(s: Seccion, offset: int) -> int:
    pagina = s.offsets[0][1] if s.offsets else (s.paginas[0] if s.paginas else 1)
    for inicio, pag in s.offsets:
        if inicio > offset:
            break
        pagina = pag
    return pagina


# ---------------------------------------------------------------- documentos genéricos

def secciones_genericas(doc: DocumentoCargado) -> list[Seccion]:
    """Documentos sin plantilla: una 'sección' por título Markdown, o una sola con todo el texto."""
    secciones: list[Seccion] = []
    actual = Seccion(None, None, "", [], [])
    for pagina in doc.paginas:
        for linea in pagina.texto.split("\n"):
            m = RE_MARKDOWN.match(linea.strip()) if doc.formato == "md" else None
            if m:
                if actual.texto.strip():
                    secciones.append(actual)
                actual = Seccion(None, m.group(1).strip(), "", [], [])
                continue
            actual.offsets.append((len(actual.texto), pagina.numero))
            actual.texto += linea + "\n"
            if pagina.numero not in actual.paginas:
                actual.paginas.append(pagina.numero)
    if actual.texto.strip():
        secciones.append(actual)
    for s in secciones:
        s.texto = s.texto.strip("\n")
    return secciones
