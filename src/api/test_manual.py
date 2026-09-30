import json
import requests

API_URL = "http://127.0.0.1:8000/query"

# Petición según el contrato QueryRequest
payload = {
    "pregunta": "¿Cuál es la dosis recomendada de paracetamol en adultos?",
    "k": 3,
    "nregistro": None
}

print("Enviando consulta a la API...")
try:
    response = requests.post(API_URL, json=payload, timeout=15)
    response.raise_for_status()
    
    data = response.json()
    
    print("\n" + "=" * 60)
    print("RESPUESTA RECIBIDA (QueryResponse):")
    print("=" * 60)
    print(f"Respuesta del LLM:\n{data.get('respuesta')}\n")
    print(f"Encontrado: {data.get('encontrado')}")
    print(f"Modelo usado: {data.get('modelo')}")
    print(f"Aviso PII: {data.get('aviso_pii')}")
    print("\nFuentes consultadas:")
    for fuente in data.get('fuentes', []):
        print(f"  [{fuente['indice']}] {fuente['nombre']} (Sec. {fuente.get('seccion')}) - Score: {fuente.get('score')}")
    print("=" * 60)

except requests.exceptions.RequestException as e:
    print(f"\nError al conectar con la API: {e}")