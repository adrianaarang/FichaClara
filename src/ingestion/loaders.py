"""Carga de documentos PDF, TXT y Markdown conservando el número de página.

Particularidades de las fichas técnicas de CIMA que se tratan aquí:
- Hay dos formatos: las nacionales (AEMPS, cabecera "1 de 5") y las centralizadas
  (EMA, nº de registro largo). Las de la EMA incluyen además los Anexos II y III
  (condiciones, etiquetado y PROSPECTO): se recortan para quedarnos solo con la ficha.
- Las tablas (p. ej. 4.8 Reacciones adversas por frecuencia) se pierden si se extraen
  como texto plano: se detectan y se convierten en frases "fila — columna: valor".

La limpieza fina del texto (cabeceras repetidas, guiones, espacios) va en cleaner.py.

Responsable: P1 · Ingesta y chunking
"""
from __future__ import annotations

import hashlib
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

logger = logging.getLogger(__name__)

EXTENSIONES_SOPORTADAS = {".pdf", ".txt", ".md", ".markdown"}
MIN_CARACTERES_POR_PAGINA = 100  # por debajo, el PDF probablemente es un escaneo sin texto

PALABRAS_FRECUENCIA = re.compile(r"frecuente|raras?\b|poco frecuente|muy rar|no conocida|frecuencia", re.IGNORECASE)


class DocumentoIlegibleError(Exception):
    """El documento no se puede leer (vacío, escaneado, protegido o corrupto)."""


class FormatoNoSoportadoError(DocumentoIlegibleError):
    """La extensión del archivo no está entre las soportadas."""


@dataclass
class Pagina:
    numero: int  # número de página real del PDF (1, 2, 3...). En TXT/MD siempre 1.
    texto: str


@dataclass
class DocumentoCargado:
    doc_id: str                 # identificador estable: FT_<nregistro> o <nombre>-<hash>
    ruta: Path
    formato: str                # "pdf" | "txt" | "md"
    es_ficha_tecnica: bool
    origen: str | None          # "aemps" | "ema" | None (no es ficha técnica)
    nregistro: str | None
    paginas: list[Pagina] = field(default_factory=list)

    @property
    def texto_completo(self) -> str:
        return "\n".join(p.texto for p in self.paginas)


# ---------------------------------------------------------------- entrada principal

def cargar_documento(ruta: Path | str) -> DocumentoCargado:
    """Carga un PDF, TXT o MD. Lanza DocumentoIlegibleError si no se puede usar."""
    ruta = Path(ruta)
    ext = ruta.suffix.lower()
    if ext not in EXTENSIONES_SOPORTADAS:
        raise FormatoNoSoportadoError(f"Formato {ext or '(sin extensión)'} no soportado. Usa PDF, TXT o MD.")
    if not ruta.exists() or ruta.stat().st_size == 0:
        raise DocumentoIlegibleError(f"{ruta.name} no existe o está vacío")

    if ext == ".pdf":
        paginas = cargar_pdf(ruta)
        formato = "pdf"
    else:
        paginas = cargar_texto(ruta)
        formato = "md" if ext in {".md", ".markdown"} else "txt"

    origen = detectar_ficha_tecnica(paginas) if formato == "pdf" else None
    if origen == "ema":
        paginas = recortar_anexos_ema(paginas)

    m = re.match(r"FT_(\d+)$", ruta.stem)
    nregistro = m.group(1) if m else None
    doc_id = f"FT_{nregistro}" if nregistro else _id_por_contenido(ruta)

    doc = DocumentoCargado(doc_id=doc_id, ruta=ruta, formato=formato, es_ficha_tecnica=origen is not None,
                           origen=origen, nregistro=nregistro, paginas=paginas)
    logger.info("Cargado %s: %d páginas, %s", ruta.name, len(paginas), origen or "documento genérico")
    return doc


# ---------------------------------------------------------------- PDF

def cargar_pdf(ruta: Path) -> list[Pagina]:
    try:
        doc = pymupdf.open(ruta)
    except Exception as e:  # PyMuPDF lanza varios tipos según el fallo
        raise DocumentoIlegibleError(f"{ruta.name} no es un PDF válido: {e}") from e

    with doc:
        if doc.needs_pass:
            raise DocumentoIlegibleError(f"{ruta.name} está protegido con contraseña")
        paginas = []
        cabecera_tabla: list[str] | None = None  # se arrastra si una tabla continúa en la página siguiente
        es_ema = doc.page_count > 0 and detectar_ficha_tecnica([Pagina(1, doc[0].get_text())]) == "ema"
        for i, page in enumerate(doc, start=1):
            texto, cabecera_tabla = _texto_de_pagina(page, cabecera_tabla)
            paginas.append(Pagina(numero=i, texto=texto))
            if es_ema and _tiene_linea_anexo_ii(texto):
                break  # lo que sigue es Anexo II, etiquetado y prospecto: no hace falta leerlo

    total = sum(len(p.texto.strip()) for p in paginas)
    if not paginas or total / len(paginas) < MIN_CARACTERES_POR_PAGINA:
        raise DocumentoIlegibleError(
            f"{ruta.name} apenas tiene texto seleccionable (¿es un escaneo?). El OCR está fuera del alcance.")
    return paginas


def _texto_de_pagina(page: pymupdf.Page, cabecera_previa: list[str] | None) -> tuple[str, list[str] | None]:
    """Texto de la página en orden de lectura, con las tablas convertidas a frases."""
    tablas = page.find_tables().tables
    rects = [pymupdf.Rect(t.bbox) for t in tablas]

    piezas: list[tuple[float, float, str]] = []
    for x0, y0, x1, y1, texto, _n, tipo in page.get_text("blocks"):
        if tipo != 0:  # 0 = texto, 1 = imagen
            continue
        centro = pymupdf.Point((x0 + x1) / 2, (y0 + y1) / 2)
        if any(centro in r for r in rects):
            continue  # ese texto ya sale en la versión linealizada de la tabla
        piezas.append((y0, x0, texto.strip()))

    cabecera = cabecera_previa
    for tabla, rect in zip(tablas, rects):
        texto_tabla, cabecera = tabla_a_texto(tabla.extract(), cabecera)
        piezas.append((rect.y0, rect.x0, texto_tabla))

    piezas.sort(key=lambda p: (round(p[0]), p[1]))
    return "\n".join(t for _, _, t in piezas if t), cabecera


def _celda(c: str | None) -> str:
    return re.sub(r"\s+", " ", (c or "").replace("-\n", "-")).strip()


def tabla_a_texto(filas: list[list[str | None]], cabecera_previa: list[str] | None = None
                  ) -> tuple[str, list[str] | None]:
    """Convierte una tabla en líneas legibles para el embedding y el LLM.

    Ejemplo: "Trastornos del sistema nervioso — Muy frecuentes: Cefalea; Frecuentes: Insomnio"
    Devuelve el texto y la cabecera usada (para continuar la tabla en la página siguiente).
    """
    filas = [[_celda(c) for c in f] for f in filas if any(_celda(c) for c in f)]
    if not filas:
        return "", cabecera_previa
    ncol = len(filas[0])

    # 1) Cabecera de frecuencias (sección 4.8): la fila con al menos 2 celdas tipo "Frecuentes"
    idx_cab = next((i for i, f in enumerate(filas[:4])
                    if sum(bool(PALABRAS_FRECUENCIA.search(c)) for c in f) >= 2), None)
    if idx_cab is not None:
        cabecera, datos = filas[idx_cab], filas[idx_cab + 1:]
    # 2) Continuación de una tabla de la página anterior (mismo nº de columnas)
    elif cabecera_previa and len(cabecera_previa) == ncol and filas[0][0] != cabecera_previa[0]:
        cabecera, datos = cabecera_previa, filas
    # 3) Tabla normal: la primera fila es la cabecera si está completa
    elif ncol > 1 and all(filas[0]) and len(filas) > 1:
        cabecera, datos = filas[0], filas[1:]
    else:
        cabecera, datos = None, filas

    lineas = ["[Tabla] " + " | ".join(c for c in cabecera if c)] if cabecera and cabecera is not cabecera_previa else []
    for fila in datos:
        if cabecera and len(cabecera) == len(fila) and ncol > 1:
            valores = [f"{cabecera[j]}: {fila[j]}" if cabecera[j] else fila[j]
                       for j in range(1, len(fila)) if fila[j]]
            lineas.append(f"{fila[0]} — {'; '.join(valores)}" if fila[0] else "; ".join(valores))
        else:
            lineas.append(" | ".join(c for c in fila if c))
    return "\n".join(lineas), cabecera


# ---------------------------------------------------------------- TXT / MD

def cargar_texto(ruta: Path) -> list[Pagina]:
    datos = ruta.read_bytes()
    for codificacion in ("utf-8-sig", "cp1252"):  # cp1252: textos guardados con el Bloc de notas antiguo
        try:
            texto = datos.decode(codificacion)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise DocumentoIlegibleError(f"No se reconoce la codificación de {ruta.name}")
    if not texto.strip():
        raise DocumentoIlegibleError(f"{ruta.name} está vacío")
    return [Pagina(numero=1, texto=texto)]


# ---------------------------------------------------------------- fichas técnicas

def detectar_ficha_tecnica(paginas: list[Pagina]) -> str | None:
    """Devuelve 'ema', 'aemps' o None si el PDF no parece una ficha técnica."""
    inicio = "\n".join(p.texto for p in paginas[:2]).upper()
    if "ANEXO I" in inicio and "RESUMEN DE LAS CARACTER" in inicio:
        return "ema"
    if "FICHA TÉCNICA" in inicio and "NOMBRE DEL MEDICAMENTO" in inicio:
        return "aemps"
    return None


def _tiene_linea_anexo_ii(texto: str) -> bool:
    return any(linea.strip().upper() == "ANEXO II" for linea in texto.splitlines())


def recortar_anexos_ema(paginas: list[Pagina]) -> list[Pagina]:
    """Se queda con el Anexo I (la ficha técnica) y descarta Anexo II, III, etiquetado y prospecto.

    También quita la portada ("ANEXO I · FICHA TÉCNICA O RESUMEN..."), que no aporta nada.
    Los números de página se conservan tal cual para poder citarlos.
    """
    resultado = []
    for p in paginas:
        lineas = p.texto.splitlines()
        corte = next((i for i, linea in enumerate(lineas) if linea.strip().upper() == "ANEXO II"), None)
        if corte is not None:
            antes = "\n".join(lineas[:corte]).strip()
            if antes:
                resultado.append(Pagina(p.numero, antes))
            break
        resultado.append(p)
    else:
        logger.warning("Ficha EMA sin 'ANEXO II': se conserva el documento completo")

    if resultado and "NOMBRE DEL MEDICAMENTO" not in resultado[0].texto.upper():
        resultado = resultado[1:]  # portada
    return resultado


def _id_por_contenido(ruta: Path) -> str:
    """Id para documentos subidos: nombre legible + huella del contenido (evita duplicados)."""
    huella = hashlib.sha1(ruta.read_bytes()).hexdigest()[:8]
    sin_tildes = unicodedata.normalize("NFKD", ruta.stem).encode("ascii", "ignore").decode()
    nombre = re.sub(r"[^a-z0-9]+", "-", sin_tildes.lower()).strip("-")[:40] or "documento"
    return f"{nombre}-{huella}"


if __name__ == "__main__":
    # Prueba manual:
    #   python -m src.ingestion.loaders data/raw/FT_11265.pdf   → muestra el texto por páginas
    #   python -m src.ingestion.loaders data/raw                → carga todas y da un resumen
    import sys
    from collections import Counter

    objetivo = Path(sys.argv[1] if len(sys.argv) > 1 else "data/raw")
    if objetivo.is_file():
        d = cargar_documento(objetivo)
        print(f"{d.doc_id} · origen={d.origen} · páginas {d.paginas[0].numero}-{d.paginas[-1].numero}\n")
        for p in d.paginas:
            print(f"==================== PÁGINA {p.numero} ====================\n{p.texto}\n")
    else:
        origenes, fallos, paginas = Counter(), [], 0
        archivos = sorted(f for f in objetivo.iterdir() if f.suffix.lower() in EXTENSIONES_SOPORTADAS)
        for n, f in enumerate(archivos, 1):
            print(f"[{n}/{len(archivos)}] {f.name}          ", end="\r", flush=True)
            try:
                d = cargar_documento(f)
                origenes[d.origen or "no es ficha"] += 1
                paginas += len(d.paginas)
            except DocumentoIlegibleError as e:
                fallos.append(f"{f.name}: {e}")
        print(f"\nArchivos: {len(archivos)} · cargados: {sum(origenes.values())} · páginas útiles: {paginas}")
        print("Por origen:", dict(origenes))
        print(f"Fallidos: {len(fallos)}")
        for linea in fallos:
            print("  ", linea)