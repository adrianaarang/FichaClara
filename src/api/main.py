# src/api/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.errors import global_exception_handler
from src.api.routes import router as api_router

app = FastAPI(
    title="FichaClara API",
    description="API para orquestación de RAG sobre Fichas Técnicas",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(Exception, global_exception_handler)

# Registro de rutas sin prefijo o con el prefijo correcto
app.include_router(api_router)