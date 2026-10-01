# src/common/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Selección de proveedor: "groq" u "ollama"
    LLM_PROVIDER: str = "ollama"

    # Configuración Groq
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # Configuración Ollama (usando tus modelos Qwen)
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "qwen2.5-coder:14b"

    # Configuración de embeddings y ChromaDB
    EMBEDDING_MODEL: str = "nomic-embed-text"
    CHROMA_DIR: str = "data/chroma"
    CHROMA_COLLECTION: str = "fichas_tecnicas"

    # Parámetros por defecto de Retrieval y API
    RETRIEVER_K: int = 5
    RELEVANCE_THRESHOLD: float = 0.3
    API_URL: str = "http://localhost:8000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()