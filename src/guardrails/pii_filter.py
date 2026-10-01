"""Filtro de datos personales en la pregunta antes de enviarla a una API comercial.

Responsable: P5 · Calidad, evaluación, DevOps y documentación

Contrato (src/common/schemas.py):  check_pii(texto) -> PiiResult
    contiene_pii      True si se detectó algún dato personal
    tipos             tipos detectados, p. ej. ['dni', 'telefono', 'nombre']
    texto_enmascarado la pregunta con cada dato sustituido por [DATO]

Qué detecta (regex + reglas, sin dependencias externas):
    dni, nie, telefono, email, historia_clinica (NHC), tarjeta_sanitaria,
    fecha_nacimiento (solo si va tras «nació el», «fecha de nacimiento»...) y
    nombre (tras «paciente», «residente», «don»... o nombre de pila + apellidos).

Qué NO hace (límites documentados en docs/etica_y_privacidad.md):
    no es un anonimizador certificado. La edad, el diagnóstico o el nombre de un
    centro no se enmascaran. Un nombre sin pista ni nombre de pila común puede pasar.

Configuración por entorno (.env):
    PII_FILTER_ENABLED=true|false   (por defecto true; false = no filtra nada)
"""

from __future__ import annotations

import os
import re

from src.common.schemas import PiiResult

MASCARA = "[DATO]"

_LETRAS_DNI = "TRWAGMYFPDXBNJZSQVHLCKE"


def _letra_dni_valida(numero: str, letra: str) -> bool:
    return _LETRAS_DNI[int(numero) % 23] == letra.upper()


def _nie_valido(nie: str) -> bool:
    prefijo = {"X": "0", "Y": "1", "Z": "2"}[nie[0].upper()]
    return _letra_dni_valida(prefijo + nie[1:8], nie[8])


# --------------------------------------------------------------------- patrones
_RE_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_RE_DNI = re.compile(r"(?<![\w])(\d{8})[\s-]?([A-Za-z])(?![\w])")
_RE_NIE = re.compile(r"(?<![\w])([XYZxyz]\d{7}[\s-]?[A-Za-z])(?![\w])")
_RE_TELEFONO = re.compile(
    r"(?<![\d])(?:(?:\+|00)34[\s.-]?)?[6789]\d{2}[\s.-]?\d{3}[\s.-]?\d{3}(?![\d])"
)
_ETIQUETA_NHC = (
    r"(?:nhc|n\.?\s?h\.?\s?c\.?|n[º°o.]{1,2}\s*(?:de\s+)?historia(?:\s+cl[ií]nica)?"
    r"|historia\s+cl[ií]nica|hist\.?\s*cl[ií]n\.?)"
)
_RE_NHC = re.compile(
    rf"(?i:\b{_ETIQUETA_NHC})[\s:#=.\-]*(?P<dato>[A-Za-z]{{0,3}}-?\d[\w-]{{2,}})"
)
_RE_TARJETA = re.compile(
    r"(?i:\b(?:tarjeta\s+sanitaria|cip|sip|n[º°o.]{1,2}\s*(?:de\s+)?afiliaci[oó]n"
    r"|seguridad\s+social))[\s:#=.\-]*(?P<dato>[A-Za-z]{0,4}\d[\w-]{4,})"
)
_RE_FECHA_NAC = re.compile(
    r"(?i:(?:naci[oó]\s+el|fecha\s+de\s+nacimiento|f\.?\s?nac\.?|nacid[oa]\s+el)"
    r"[\s:]*)(?P<dato>\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})"
)

_PALABRA_NOMBRE = r"[A-ZÁÉÍÓÚÑ][a-záéíóúñü]+"
_PARTICULA = r"(?:de(?:l)?|de\s+la|de\s+los|de\s+las|y)"
_NOMBRE_COMPLETO = (
    rf"{_PALABRA_NOMBRE}(?:\s+(?:{_PARTICULA}\s+)?{_PALABRA_NOMBRE}){{0,3}}"
)
_RE_NOMBRE_CON_PISTA = re.compile(
    r"(?:(?i:\b(?:paciente|residente|sr\.?|sra\.?|se[ñn]or|se[ñn]ora|don|do[ñn]a|"
    r"d\.|d[ñn]a\.?|llamad[oa]|se\s+llama|nombre)\b)[\s:]+)"
    rf"(?P<dato>{_NOMBRE_COMPLETO})"
)

_NOMBRES_DE_PILA = frozenset(
    (
        "Antonio",
        "Manuel",
        "José",
        "Francisco",
        "David",
        "Juan",
        "Javier",
        "Daniel",
        "Carlos",
        "Miguel",
        "Rafael",
        "Pedro",
        "Ángel",
        "Alejandro",
        "Fernando",
        "Luis",
        "Sergio",
        "Pablo",
        "Jorge",
        "Alberto",
        "Álvaro",
        "Adrián",
        "Diego",
        "Iván",
        "Rubén",
        "Raúl",
        "Enrique",
        "Ramón",
        "Vicente",
        "Andrés",
        "Joaquín",
        "Santiago",
        "Jesús",
        "Mario",
        "Óscar",
        "Marcos",
        "Víctor",
        "Gonzalo",
        "Ignacio",
        "Salvador",
        "Emilio",
        "Tomás",
        "Julián",
        "Eduardo",
        "Felipe",
        "Roberto",
        "Ricardo",
        "María",
        "Carmen",
        "Josefa",
        "Isabel",
        "Ana",
        "Dolores",
        "Pilar",
        "Teresa",
        "Laura",
        "Cristina",
        "Marta",
        "Lucía",
        "Elena",
        "Francisca",
        "Rosa",
        "Paula",
        "Concepción",
        "Mercedes",
        "Antonia",
        "Raquel",
        "Beatriz",
        "Rocío",
        "Silvia",
        "Patricia",
        "Montserrat",
        "Nuria",
        "Sara",
        "Irene",
        "Julia",
        "Inmaculada",
        "Amparo",
        "Encarnación",
        "Manuela",
        "Remedios",
        "Milagros",
        "Consuelo",
        "Gloria",
        "Angustias",
        "Soledad",
        "Yolanda",
        "Eva",
        "Sonia",
        "Susana",
        "Lourdes",
        "Juana",
        "Yohanna",
        "Yohana",
        "Adriana",
    )
)
_RE_NOMBRE_DE_PILA = re.compile(
    rf"(?<![\wÁÉÍÓÚÑáéíóúñ])(?P<dato>(?:{'|'.join(sorted(_NOMBRES_DE_PILA))})"
    rf"(?:\s+(?:{_PARTICULA}\s+)?{_PALABRA_NOMBRE}){{1,3}})(?![\wáéíóúñ])"
)

# (tipo, patrón, grupo a enmascarar o None = todo el patrón)
_REGLAS: list[tuple[str, re.Pattern[str], str | None]] = [
    ("email", _RE_EMAIL, None),
    ("nie", _RE_NIE, None),
    ("dni", _RE_DNI, None),
    ("telefono", _RE_TELEFONO, None),
    ("historia_clinica", _RE_NHC, "dato"),
    ("tarjeta_sanitaria", _RE_TARJETA, "dato"),
    ("fecha_nacimiento", _RE_FECHA_NAC, "dato"),
    ("nombre", _RE_NOMBRE_CON_PISTA, "dato"),
    ("nombre", _RE_NOMBRE_DE_PILA, "dato"),
]


def _filtro_activo() -> bool:
    return os.environ.get("PII_FILTER_ENABLED", "true").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _detectar(texto: str) -> list[tuple[int, int, str]]:
    """Devuelve tramos (inicio, fin, tipo) sin solapes; gana el primero en prioridad."""
    tramos: list[tuple[int, int, str]] = []
    for tipo, patron, grupo in _REGLAS:
        for m in patron.finditer(texto):
            if grupo:
                ini, fin = m.span(grupo)
            else:
                ini, fin = m.span()
            if any(ini < f and fin > i for i, f, _ in tramos):
                continue
            tramos.append((ini, fin, tipo))
    return sorted(tramos)


def check_pii(texto: str) -> PiiResult:
    """Detecta datos personales en ``texto`` y devuelve la versión enmascarada."""
    if not texto or not _filtro_activo():
        return PiiResult(contiene_pii=False, tipos=[], texto_enmascarado=texto or "")

    tramos = _detectar(texto)
    if not tramos:
        return PiiResult(contiene_pii=False, tipos=[], texto_enmascarado=texto)

    partes: list[str] = []
    cursor = 0
    for ini, fin, _ in tramos:
        partes.append(texto[cursor:ini])
        partes.append(MASCARA)
        cursor = fin
    partes.append(texto[cursor:])

    tipos = list(dict.fromkeys(tipo for _, _, tipo in tramos))
    return PiiResult(contiene_pii=True, tipos=tipos, texto_enmascarado="".join(partes))
