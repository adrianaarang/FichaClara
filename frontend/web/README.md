# FichaClara · interfaz web

Interfaz en HTML + CSS + JavaScript puros (sin Streamlit, sin `npm`, sin compilar nada).
Habla con la API FastAPI: `POST /query`, `POST /ingest`, `GET /documents`, `DELETE /documents/{id}` y `GET /health`.

## Cómo verla

1. Arranca la API (desde la raíz del repo): `uvicorn src.api.main:app --port 8000`
2. Sirve esta carpeta:
   ```
   python -m http.server 5173 --directory frontend/web
   ```
3. Abre <http://localhost:5173>

- **Modo demo** (sin API): <http://localhost:5173/?mock=1> usa respuestas falsas de `mock.js`, que siguen el contrato de `src/common/schemas.py`.
- **Otra URL de la API**: `?api=http://otro-host:8000`, o define `window.FICHACLARA_API` antes de cargar `app.js`.

La API ya permite cualquier origen (CORS), así que no hace falta configurar nada más.

## Qué incluye

- Chat con respuesta escrita poco a poco, citas `[n]` clicables que abren y resaltan la fuente, y tarjetas de fuente (sección, página, fragmento, relevancia, fecha de revisión y enlace).
- Estado diferenciado para `encontrado: false` y aviso cuando `aviso_pii: true`.
- Aviso sanitario permanente.
- Panel de documentos: subida con arrastrar y soltar, aviso de privacidad, búsqueda, borrado con confirmación.
- Adaptado a móvil, con `prefers-reduced-motion` y teclado (Enter envía, Shift+Enter salta de línea).

## Archivos

| Archivo | Para qué |
|---|---|
| `index.html` | estructura y mascota (SVG reutilizable) |
| `styles.css` | estilos y animaciones; paleta sacada del logo |
| `app.js` | lógica, llamadas a la API y render |
| `mock.js` | API de mentira para el modo demo |
| `assets/` | logo, símbolo y favicon (copiados de `fichaclara-logo/`) |

El texto que devuelve el modelo se escapa antes de pintarlo, y los enlaces de las fuentes solo se abren si son `http(s)`.
