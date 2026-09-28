"""Limpieza del texto extraído de los documentos.

Se aplica página a página (para no perder el nº de página que luego se cita) y deja
el texto listo para el chunker:

1. Caracteres raros de PDF: espacios duros, guiones invisibles, ligaduras y la viñeta
   de la fuente Symbol, que se ve como un cuadrado.
2. Números de página sueltos ("1 de 5", "29") y líneas que se repiten en casi
   todas las páginas (cabeceras y pies).
3. Viñetas partidas en dos líneas ("•" en una, el texto en la siguiente).
4. Títulos de sección de la EMA partidos ("4.2" en una línea, "Posología..." en la
   siguiente): se unen en "4.2 Posología...", igual que en las fichas nacionales.
5. Palabras cortadas con guion al final de línea ("exten-\\nsamente").
6. Líneas de un mismo párrafo cortadas por el ancho de la página: se unen.
7. Espacios y líneas en blanco de más.

Responsable: P1 · Ingesta y chunking
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import replace

from src.ingestion.loaders import DocumentoCargado, Pagina

REEMPLAZOS = {
    "\u00a0": " ",  # espacio duro
    "\u2009": " ",  # espacio fino
    "\u202f": " ",  # espacio fino no separable
    "\u00ad": "",  # guion invisible (soft hyphen)
    "\u200b": "",  # espacio de ancho cero
    "\ufb01": "fi",  # ligadura fi
    "\ufb02": "fl",  # ligadura fl
    "\u2010": "-",  # guion tipográfico
    "\u2011": "-",  # guion no separable
    "\uf0b7": "•",  # viñeta de la fuente Symbol
    "\uf0a7": "•",  # viñeta de la fuente Symbol
    "\uf02d": "-",  # guion de la fuente Symbol
    "\t": " ",
}
VINETAS = "•▪◦●○■□➢►-–*"

RE_NUMERO_PAGINA = re.compile(r"^\s*(?:página\s*)?\d{1,3}(?:\s*(?:de|/)\s*\d{1,3})?\s*$", re.IGNORECASE)
RE_NUMERO_SECCION = re.compile(r"^\d{1,2}(?:\.\d{1,2}){0,2}\.?$")          # "4.", "4.2", "4.2.1"
RE_VINETA_SOLA = re.compile(rf"^[{re.escape(VINETAS)}]$")
RE_GUION_FIN = re.compile(r"([a-záéíóúüñ])-\n([a-záéíóúüñ])")            # exten-\nsamente
RE_FLECHA_VACIA = re.compile(r"\s+—\s*$")                                 # fila de tabla sin valores
RE_ENCABEZADO = re.compile(r"^\d{1,2}(?:\.\d{1,2}){0,2}\.? +[A-ZÁÉÍÓÚÑ]")        # "4.2. Posología" (no "48 horas")
RE_ESPACIO_ANTES_PUNTO = re.compile(r"^(\d{1,2}) \.(?=\s)")                   # "6 . DATOS" → "6. DATOS"
RE_TITULO = re.compile(r"^\d{1,2}(?:\.\d{1,2}){0,2}\.? +\S")                  # "4.2. Posología", "10. FECHA"


# ---------------------------------------------------------------- entrada principal

def limpiar_documento(doc: DocumentoCargado) -> DocumentoCargado:
    """Devuelve una copia del documento con todas sus páginas limpias.

    Las páginas que se quedan vacías tras limpiar se eliminan (conservando la
    numeración original de las demás).
    """
    paginas = [Pagina(p.numero, normalizar_caracteres(p.texto)) for p in doc.paginas]
    paginas = quitar_numeros_de_pagina(paginas)
    paginas = quitar_lineas_repetidas(paginas)
    limpias = [Pagina(p.numero, limpiar_texto(p.texto)) for p in paginas]
    return replace(doc, paginas=[p for p in limpias if p.texto])


def limpiar_texto(texto: str) -> str:
    """Limpieza de una página (o de un texto suelto, p. ej. un .txt)."""
    texto = normalizar_caracteres(texto)
    lineas = [re.sub(r" {2,}", " ", linea).strip() for linea in texto.splitlines()]
    lineas = [RE_ESPACIO_ANTES_PUNTO.sub(r"\1.", RE_FLECHA_VACIA.sub("", linea)) for linea in lineas]
    lineas = unir_vinetas_y_titulos(lineas)
    texto = "\n".join(lineas)
    texto = RE_GUION_FIN.sub(r"\1\2", texto)
    texto = unir_lineas_de_parrafo(texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


# ---------------------------------------------------------------- piezas

def normalizar_caracteres(texto: str) -> str:
    texto = unicodedata.normalize("NFC", texto)
    for malo, bueno in REEMPLAZOS.items():
        texto = texto.replace(malo, bueno)
    return texto


def quitar_numeros_de_pagina(paginas: list[Pagina]) -> list[Pagina]:
    """Quita "1 de 5", "Página 3" o "29" cuando están en la primera o la última línea con texto."""
    resultado = []
    for p in paginas:
        lineas = p.texto.splitlines()
        con_texto = [i for i, linea in enumerate(lineas) if linea.strip()]
        for i in con_texto[:2] + con_texto[-2:]:
            # Sin punto: "4." o "4.2" son títulos de sección, "29" o "3 de 8" son nº de página
            if RE_NUMERO_PAGINA.match(lineas[i]) and "." not in lineas[i]:
                lineas[i] = ""
        resultado.append(Pagina(p.numero, "\n".join(lineas)))
    return resultado


def quitar_lineas_repetidas(paginas: list[Pagina], umbral: float = 0.6) -> list[Pagina]:
    """Quita cabeceras/pies: líneas que aparecen al principio o al final de más del 60 % de las páginas."""
    if len(paginas) < 3:
        return paginas

    def extremos(texto: str) -> set[str]:
        lineas = [linea.strip() for linea in texto.splitlines() if linea.strip()]
        return set(lineas[:3] + lineas[-3:])

    cuenta = Counter(linea for p in paginas for linea in extremos(p.texto))
    repetidas = {linea for linea, n in cuenta.items() if n / len(paginas) > umbral and len(linea) > 3}
    if not repetidas:
        return paginas
    return [Pagina(p.numero, "\n".join(linea for linea in p.texto.splitlines() if linea.strip() not in repetidas))
            for p in paginas]


def unir_vinetas_y_titulos(lineas: list[str]) -> list[str]:
    """Une una viñeta o un número de sección sueltos con la siguiente línea con texto."""
    resultado: list[str] = []
    pendiente: str | None = None
    for linea in lineas:
        if pendiente is not None:
            if not linea:
                continue  # salta líneas en blanco entre "4.2" y "Posología"
            resultado.append(f"{pendiente} {linea}")
            pendiente = None
        elif RE_VINETA_SOLA.match(linea):
            pendiente = "•" if linea != "-" else "-"
        elif RE_NUMERO_SECCION.match(linea) and "." in linea:
            pendiente = linea
        else:
            resultado.append(linea)
    if pendiente is not None:
        resultado.append(pendiente)
    return resultado


def unir_lineas_de_parrafo(texto: str) -> str:
    """Une líneas cortadas por el ancho de página.

    Solo une si la línea anterior no acaba en puntuación final y la siguiente empieza en
    minúscula, por número o paréntesis (sin ser un título de sección) o por coma. Nunca une
    líneas que empiezan en mayúscula: suelen ser subtítulos ("Insuficiencia renal").
    """
    lineas = texto.split("\n")
    resultado: list[str] = []
    for linea in lineas:
        anterior = resultado[-1] if resultado else ""
        abierta = bool(anterior) and not anterior.endswith((".", ":", ";", "?", "!"))
        es_tabla = anterior.startswith("[Tabla]") or " — " in anterior or " — " in linea
        if not linea or not abierta or es_tabla:
            resultado.append(linea)
        elif RE_TITULO.match(anterior):
            # Un título solo se une con su propia continuación en mayúsculas
            # ("9. FECHA DE LA PRIMERA AUTORIZACIÓN/RENOVACIÓN DE LA" + "AUTORIZACIÓN"),
            # nunca con el texto de la sección ("10. FECHA DE LA REVISIÓN DEL TEXTO" + "noviembre 2023").
            if linea.isupper() and anterior.split(" ", 1)[-1].isupper():
                resultado[-1] = f"{anterior} {linea}"
            else:
                resultado.append(linea)
        elif linea[0].islower():
            resultado[-1] = f"{anterior} {linea}"
        elif linea[0] in ",;)":
            resultado[-1] = f"{anterior}{linea}"          # "(≥1/10)" + ", frecuentes"
        elif (linea[0].isdigit() or linea[0] == "(") and len(anterior) >= 70 and not RE_ENCABEZADO.match(linea):
            # Solo si la línea anterior llega casi al margen (la cortó el ancho de página):
            # "…debe hacerse gradualmente y finalizarse unas" + "48 horas antes…"
            resultado[-1] = f"{anterior} {linea}"
        else:
            resultado.append(linea)
    return "\n".join(resultado)


if __name__ == "__main__":
    # Prueba manual:  python -m src.ingestion.cleaner data/raw/FT_54503.pdf
    import sys

    from src.ingestion.loaders import cargar_documento

    original = cargar_documento(sys.argv[1])
    limpio = limpiar_documento(original)
    for p in limpio.paginas:
        print(f"==================== PÁGINA {p.numero} ====================\n{p.texto}\n")
    antes, despues = len(original.texto_completo), len(limpio.texto_completo)
    print(f"Caracteres: {antes} → {despues} ({antes - despues} eliminados)")
