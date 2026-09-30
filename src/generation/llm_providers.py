from langchain_core.language_models import BaseChatModel
from langchain_groq import ChatGroq
from langchain_ollama import ChatOllama
from src.common.config import settings

def get_llm() -> tuple[BaseChatModel, str]:
    """Retorna una instancia del LLM según la configuración y el nombre del modelo."""
    provider = settings.LLM_PROVIDER.lower()
    
    if provider == "groq":
        llm = ChatGroq(
            api_key=settings.GROQ_API_KEY,
            model_name=settings.GROQ_MODEL,
            temperature=0.0
        )
        model_name = f"groq/{settings.GROQ_MODEL}"
    elif provider == "ollama":
        llm = ChatOllama(
            base_url=settings.OLLAMA_BASE_URL,
            model=settings.OLLAMA_MODEL,
            temperature=0.0
        )
        model_name = f"ollama/{settings.OLLAMA_MODEL}"
    else:
        raise ValueError(f"Proveedor de LLM no soportado: {provider}")
        
    return llm, model_name