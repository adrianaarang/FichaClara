"""Contratos compartidos entre módulos de FichaClara.

Chicos, esto es el "idioma común" del proyecto: lo que genera cada uno y lo que
reciben los demás. Si todos programamos contra estas clases, podemos trabajar en
paralelo aunque el módulo del otro todavía no esté terminado.

Cualquier cambio aquí va en una PR aprobada por 2 personas y avisando en el grupo,
porque si cambia un campo se le rompe el código a otra persona.

    Quién produce                  Qué                          Quién lo usa
    ─────────────────────────────  ───────────────────────────  ──────────────────
    Adriana (P1 · ingesta)         Chunk, ChunkMetadata         David, Yohana
    David   (P2 · retrieval)       RetrievedChunk               Josema, Yohana
    Yohana  (P5 · guardrails)      PiiResult                    Josema
    Josema  (P3 · API)             QueryRequest, QueryResponse, Anas, Yohana
                                   Fuente, IngestResponse,
                                   DocumentoIndexado

Custodia: Josema (P3) · Propuesta inicial: Adriana (P1) · Versión 1
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

TipoDocumento = Literal["ficha_tecnica", "documento"]
Origen = Literal["aemps", "ema"]


# ====================================================================== Adriana (P1) → David (P2)
# Esto lo genero yo en el chunker y lo guardo en data/processed/chunks.jsonl
# (una línea por chunk, con Chunk.model_dump_json()).
#   · David: es lo que conviertes en embeddings y metes en Chroma. Usa chunk_id como
#     id en Chroma y metadata.a_chroma() para los metadatos.
#   · Yohana: para el golden set, la respuesta esperada de cada pregunta es un
#     (nregistro, seccion). Con eso puedes medir si el retriever acierta.

class ChunkMetadata(BaseModel):
    """Metadatos de un fragmento. Sirven para citar la fuente y para filtrar la búsqueda."""

    chunk_id: str = Field(description="Único y estable: '<doc_id>::<seccion>::<parte>'. Permite reindexar sin duplicar.")
    doc_id: str = Field(description="'FT_<nregistro>' para fichas, '<nombre>-<huella>' para documentos subidos")
    tipo_documento: TipoDocumento
    nombre: str = Field(description="Nombre del medicamento, o nombre del archivo si no es ficha técnica")

    # Solo fichas técnicas (None en documentos subidos)
    nregistro: str | None = None
    principios_activos: str | None = Field(None, description="Separados por comas, como en CIMA")
    atc: str | None = None
    origen: Origen | None = Field(None, description="'aemps' (nacional) o 'ema' (centralizada)")
    fecha_revision: str | None = Field(None, description="Texto de la sección 10, p. ej. 'Julio 2024'")

    # Posición dentro del documento
    seccion: str | None = Field(None, description="Número de sección: '4.2', '6.6'... None si el documento no tiene secciones")
    titulo_seccion: str | None = Field(None, description="'Posología y forma de administración'")
    pagina_inicio: int = Field(ge=1)
    pagina_fin: int = Field(ge=1)
    orden: int = Field(ge=0, description="Posición del chunk dentro del documento (0, 1, 2...)")
    parte: int = Field(1, ge=1, description="Si una sección se divide en varios chunks: 1, 2, 3...")
    total_partes: int = Field(1, ge=1)

    url_fuente: str | None = Field(None, description="Enlace para abrir la fuente (en fichas, la sección concreta en CIMA)")

    def a_chroma(self) -> dict[str, str | int | float | bool]:
        """Metadatos en el formato que acepta ChromaDB: sin valores None.

        David: Chroma da error si le pasas un None en los metadatos, por eso esto.
        """
        return {k: v for k, v in self.model_dump().items() if v is not None}


class Chunk(BaseModel):
    """Fragmento listo para indexar.

    'texto' es lo que se convierte en embedding y lo que ve el LLM. Empieza con una
    cabecera de contexto ("[Lopresor 100 mg · 4.5 Interacción...]") para que un trozo
    suelto sepa de qué medicamento y sección habla.
    """

    texto: str = Field(min_length=1)
    metadata: ChunkMetadata


# ====================================================================== David (P2) → Josema (P3)
# Lo que devuelve retrieve(pregunta, k) de David.
#   · Josema: si la lista viene vacía (nada supera el umbral), no llames al LLM y
#     devuelve QueryResponse(encontrado=False).
#   · Yohana: con esto calculas hit rate@k y MRR para el checkpoint de retrieval.

class RetrievedChunk(BaseModel):
    """Chunk devuelto por el retriever, con su puntuación de relevancia."""

    chunk: Chunk
    score: float = Field(description="Mayor = más relevante. David documenta la escala (coseno 0-1).")


# ====================================================================== Yohana (P5) → Josema (P3)
# Lo que devuelve check_pii(pregunta) de Yohana.
#   · Josema: si contiene_pii es True, envía texto_enmascarado al LLM comercial
#     (nunca la pregunta original) y pon aviso_pii=True en la respuesta.

class PiiResult(BaseModel):
    """Resultado del filtro de datos personales sobre la pregunta del usuario."""

    contiene_pii: bool
    tipos: list[str] = Field(default_factory=list, description="p. ej. ['dni', 'telefono', 'nombre']")
    texto_enmascarado: str = Field(description="La pregunta con los datos personales sustituidos por [DATO]")


# ====================================================================== API: Josema (P3) → Anas (P4)
# Lo que envían y reciben los endpoints de Josema.
#   · Anas: es exactamente lo que tiene que devolver tu mock_api.py mientras la API
#     no esté lista. Cuando Josema la termine, solo cambias la URL.
#   · Yohana: eval_generation.py puede llamar a POST /query y comprobar las citas
#     y el campo 'encontrado'.

class QueryRequest(BaseModel):
    pregunta: str = Field(min_length=3, max_length=1000)
    k: int | None = Field(None, ge=1, le=20, description="Nº de fragmentos a recuperar. None = valor por defecto")
    nregistro: str | None = Field(None, description="Limitar la búsqueda a un medicamento concreto")


class Fuente(BaseModel):
    """Lo que el frontend muestra en el panel de fuentes.

    Anas: 'indice' es el [n] que aparece en el texto de la respuesta, para que puedas
    enlazar cada cita con su fuente. 'url' abre la sección exacta en CIMA.
    """

    indice: int = Field(ge=1, description="El número [n] con el que se cita en la respuesta")
    doc_id: str
    nombre: str
    seccion: str | None = None
    titulo_seccion: str | None = None
    pagina: int = Field(ge=1)
    fragmento: str = Field(description="Texto del chunk (se muestra resaltado)")
    url: str | None = None
    fecha_revision: str | None = None
    score: float


class QueryResponse(BaseModel):
    """Anas: si encontrado es False, muéstralo distinto a una respuesta normal
    (es el "no consta en las fichas consultadas"). Si aviso_pii es True, enseña un aviso
    de que la pregunta tenía datos personales."""

    respuesta: str
    encontrado: bool = Field(description="False si no hubo contexto relevante (no se llamó al LLM)")
    fuentes: list[Fuente] = Field(default_factory=list)
    aviso_pii: bool = Field(False, description="True si la pregunta contenía datos personales")
    modelo: str | None = Field(None, description="Proveedor y modelo usados, p. ej. 'groq/llama-3.3-70b'")


class IngestResponse(BaseModel):
    """Respuesta de POST /ingest. Josema la construye con mi cargar_documento() + el chunker
    y las funciones de David para indexar."""

    doc_id: str
    nombre: str
    tipo_documento: TipoDocumento
    paginas: int
    chunks: int
    ya_existia: bool = Field(False, description="True si el documento ya estaba indexado (se reemplazó)")


class DocumentoIndexado(BaseModel):
    """Elemento de la lista GET /documents."""

    doc_id: str
    nombre: str
    tipo_documento: TipoDocumento
    chunks: int
