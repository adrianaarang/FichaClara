# File: frontend/app.py

import base64
import os
import time
from datetime import datetime, timezone

import streamlit as st
from components.source_panel import render_source_card
from components.styles import apply_fichaclara_theme

# Toggle between Mock and Real API
USE_MOCK = os.getenv("USE_MOCK_API", "true").lower() == "true"
if USE_MOCK:
    from mock_api import ask_question
else:
    from api_client import ask_question

st.set_page_config(
    page_title="FichaClara · Workspace",
    page_icon="💊",
    layout="wide",
    initial_sidebar_state="expanded"
)

apply_fichaclara_theme()

# --- Helper: Convert local image to Base64 for HTML embedding ---
def get_image_base64(path):
    try:
        with open(path, "rb") as img_file:
            return base64.b64encode(img_file.read()).decode()
    except OSError:  # <--- Change this line
        return ""

# --- Authentication & URL Parameter Check ---
query_params = st.query_params
passed_token = query_params.get("token", "dev_token_123")
passed_role = query_params.get("role", "Investigador / Org")

if not passed_token or not passed_role:
    st.error("Acceso denegado. Por favor, inicia sesión desde la página principal de FichaClara.")
    st.stop()

# --- Session State Initialization ---
if "view" not in st.session_state:
    st.session_state.view = "workspace" 
if "user_role" not in st.session_state:
    st.session_state.user_role = passed_role
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "documents" not in st.session_state:
    st.session_state.documents = [
        {"name": "Ibuprofeno_CIMA.pdf", "status": "✓ Indexado", "date": "06/10/2026", "sections": 42}
    ]

def navigate_to(view):
    st.session_state.view = view
    st.rerun()

# --- GEMINI-STYLE DARK SIDEBAR ---
def render_sidebar():
    with st.sidebar:
        st.markdown("""
            <style>
            @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600&display=swap');
            
            /* 1. Narrow the sidebar */
            [data-testid="stSidebar"] {
                min-width: 260px !important;
                max-width: 260px !important;
                background-color: #1E1F22 !important; /* Deep Dark Gray */
                border-right: none !important;
            }
            
            /* 2. Apply font SAFELY so we don't break Streamlit's icons (Fixes "keyboard_double_a") */
            [data-testid="stSidebar"] p, 
            [data-testid="stSidebar"] a,
            [data-testid="stSidebar"] div.sidebar-logo,
            [data-testid="stSidebar"] div.profile-badge {
                font-family: 'Outfit', sans-serif !important;
            }
            
            .sidebar-logo {
                font-size: 1.45rem;
                font-weight: 700;
                color: #E3E3E3 !important;
                margin-bottom: 0.2rem;
                display: flex;
                align-items: center;
                justify-content: flex-start;
                gap: 12px;
                letter-spacing: -0.5px;
            }
            
            .sidebar-logo img {
                width: 32px;
                height: 32px;
                border-radius: 6px;
            }
            
            .profile-badge {
                background-color: #333639 !important;
                color: #E3E3E3 !important;
                padding: 4px 10px;
                border-radius: 6px;
                font-size: 0.7rem;
                font-weight: 600;
                letter-spacing: 0.5px;
                margin-bottom: 2rem;
                display: inline-block;
                text-align: left;
            }
            
            /* 3. Fix Sidebar Buttons - Left Aligned, No White Shadows */
            [data-testid="stSidebar"] div.stButton > button {
                background-color: transparent !important;
                border: none !important;
                box-shadow: none !important;
                border-radius: 50px !important;
                padding: 0.65rem 1.2rem !important;
                width: 100% !important;
                display: flex !important;
                justify-content: flex-start !important;
                transition: background-color 0.2s ease !important;
                margin-bottom: 0.2rem !important;
            }
            
            [data-testid="stSidebar"] div.stButton > button:hover {
                background-color: #333639 !important; 
            }
            
            /* Force text inside button to left align */
            [data-testid="stSidebar"] div.stButton > button div[data-testid="stMarkdownContainer"] {
                width: 100% !important;
                text-align: left !important;
            }
            
            [data-testid="stSidebar"] div.stButton > button p {
                margin: 0 !important;
                text-align: left !important;
                font-size: 0.95rem !important;
                font-weight: 500 !important;
                color: #C4C7C5 !important;
            }
            
            /* Active Button (Chat / Consultas) */
            [data-testid="stSidebar"] div.stButton > button[kind="primary"] {
                background-color: #004A77 !important;
            }
            
            [data-testid="stSidebar"] div.stButton > button[kind="primary"] p {
                color: #C2E7FF !important;
                font-weight: 600 !important;
            }
            
            /* Privacy Card */
            .pii-warning {
                background-color: #1E1E1E !important;
                border: 1px solid #444746 !important;
                padding: 1rem;
                border-radius: 16px;
                font-size: 0.85rem;
                line-height: 1.5;
                margin-top: 2rem;
                margin-bottom: 1rem;
                text-align: left;
                font-family: 'Outfit', sans-serif !important;
                color: #E3E3E3 !important;
            }
            
            .pii-warning strong {
                color: #F2B8B5 !important;
                font-weight: 600;
                display: flex;
                align-items: center;
                justify-content: flex-start;
                gap: 6px;
                margin-bottom: 6px;
                font-size: 0.9rem;
            }
            
            /* Logout */
            .logout-container {
                display: flex;
                align-items: center;
                justify-content: flex-start;
                gap: 12px;
                padding: 0.8rem 1.2rem;
                border-radius: 50px;
                text-decoration: none !important;
                font-weight: 500;
                font-size: 0.95rem;
                transition: background-color 0.2s;
                margin-top: 1rem;
                width: 100%;
                color: #C4C7C5 !important;
                font-family: 'Outfit', sans-serif !important;
            }
            .logout-container:hover {
                background-color: #333639 !important;
                color: #E3E3E3 !important;
            }
            </style>
        """, unsafe_allow_html=True)
        
        # Load sidebar logo via Base64 
        icon_path = "fichaclara-logo/fichaclara-icono-app-512.png"
        icon_b64 = get_image_base64(icon_path)
        logo_html = f'<img src="data:image/png;base64,{icon_b64}">' if icon_b64 else '⚕️'
        
        st.markdown(f'<div class="sidebar-logo">{logo_html} FichaClara</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="profile-badge">{st.session_state.user_role.upper()}</div>', unsafe_allow_html=True)
        
        if st.button("💬 Chat / Consultas", use_container_width=True, type="primary" if st.session_state.view == "workspace" else "secondary"):
            navigate_to("workspace")
            
        st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)
        
        if st.button("➕ Nueva conversación", use_container_width=True):
            st.session_state.chat_history = []
            navigate_to("workspace")
            
        st.markdown(
            """
            <div class="pii-warning">
                <strong>⚠️ Privacidad</strong>
                No introduzcas identificadores<br>de pacientes.
            </div>
            """,
            unsafe_allow_html=True
        )
        
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(
            """
            <a href="http://localhost:5173" target="_self" class="logout-container">
                <span>🚪</span>
                <span>Cerrar sesión</span>
            </a>
            """, 
            unsafe_allow_html=True
        )

# --- WORKSPACE (Chat) ---
def render_workspace():
    render_sidebar()
    
    st.markdown("<h3 style='color: #8AB4F8;'>Asistente Documental CIMA</h3>", unsafe_allow_html=True)

    # --- EMPTY STATE ---
    if not st.session_state.chat_history:
        st.markdown("<div style='height: 15vh;'></div>", unsafe_allow_html=True)
        
        # Insert main horizontal logo securely centered
        logo_path = "fichaclara-logo/fichaclara-logo-horizontal-oscuro.png"
        _, col_logo, _ = st.columns([1, 2, 1])
        with col_logo:
            if os.path.exists(logo_path):
                logo_b64 = get_image_base64(logo_path)
                st.markdown(f'<div style="text-align: center;"><img src="data:image/png;base64,{logo_b64}" style="width: 80%; max-width: 400px; filter: invert(1) brightness(2);"></div>', unsafe_allow_html=True)
            else:
                st.markdown("<h1 style='text-align: center; color: #8AB4F8;'>FichaClara</h1>", unsafe_allow_html=True)
                
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("<p style='text-align: center; color: #9AA0A6; font-size: 1.1rem; margin-bottom: 1rem;'>¿Sobre qué medicamento deseas consultar?</p>", unsafe_allow_html=True)
        
        chips = [
            "¿Qué interacciones tiene el Ibuprofeno?",
            "¿Cuáles son las reacciones adversas descritas?",
            "¿Qué indica la sección 4.5?"
        ]
        chip_cols = st.columns(len(chips))
        for i, text in enumerate(chips):
            if chip_cols[i].button(text, key=f"chip_{i}", use_container_width=True):
                process_query(text)
                st.rerun()

    # Display chat history if it exists
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            if msg["role"] == "assistant" and msg.get("sources"):
                with st.expander("📄 Ver fuentes oficiales"):
                    for src in msg["sources"]:
                        render_source_card(src)

    # --- YOUR EXACT POPOVER RATIOS WITH DARK MODE COLORS ---
    st.markdown("""
        <style>
        div[data-testid="stPopover"] {
            display: flex !important;
            justify-content: center !important; 
            width: 3000% !important;
            margin-top: -7px !important;
            margin-bottom: -100px !important; 
        }
        
        button[data-testid="stPopoverButton"] {
            width: fit-content !important; 
            border-radius: 24px !important; 
            border: 1px solid #444746 !important; 
            background-color: #1E1F22 !important; 
            color: #E3E3E3 !important;
            padding: 0.5rem 1.5rem !important;
            font-size: 0.95rem !important;
            font-weight: 500 !important;
            transition: all 0.2s ease;
        }
        
        button[data-testid="stPopoverButton"]:hover {
            background-color: #333639 !important; 
            border-color: #8AB4F8 !important;
        }

        button[data-testid="stPopoverButton"] p {
            white-space: nowrap !important;
            overflow: visible !important;
            margin: 0 !important;
        }

        button[data-testid="stPopoverButton"] svg, 
        button[data-testid="stPopoverButton"] div[aria-hidden="true"] {
            display: none !important;
        }
        </style>
    """, unsafe_allow_html=True)

    # 1. Render Popover with your requested text
    with st.popover("➕ Añadir Documento"):
        st.write("**Subir archivo rápido**")
        quick_upload = st.file_uploader(
            "Sube un PDF, imagen o ficha técnica", 
            type=["pdf", "txt", "png", "jpg", "jpeg"], 
            label_visibility="collapsed",
            key="chat_attachment_uploader"
        )
        if quick_upload:
            st.session_state.documents.insert(0, {
                "name": quick_upload.name, # <--- Change this back to uploaded_file
                "status": "✓ Indexado",
                "date": datetime.now(timezone.utc).strftime('%d/%m/%Y'),
                "sections": 28
            })
            st.success(f"Archivo {quick_upload.name} procesado.")
            time.sleep(1)
            st.rerun()
            
        st.markdown("---")
        if st.button("📄 Ir a Gestión de Documentos", use_container_width=True, key="popover_doc_btn"):
            navigate_to("documents")

    # 2. Render Chat Input normally at the bottom
    if query := st.chat_input("Escribe una pregunta sobre la ficha técnica...", key="main_chat_input"):
        process_query(query)
        st.rerun()

def process_query(query: str):
    st.session_state.chat_history.append({"role": "user", "content": query})
    response = ask_question(query)

    if not response.get("found", False):
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": f"ℹ {response.get('answer', 'Información no encontrada.')}",
            "sources": []
        })
    else:
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": response.get("answer"),
            "sources": response.get("sources", [])
        })

# --- DOCUMENT MANAGEMENT ---
def render_document_management():
    render_sidebar()
    st.markdown("<h3 style='color: #8AB4F8; margin-top: -1rem;'>Base de conocimiento local</h3>", unsafe_allow_html=True)
    
    with st.container(border=True):
        uploaded_file = st.file_uploader("Subir nueva ficha técnica", type=["pdf"], key="doc_management_uploader")
        if uploaded_file is not None:
            status_container = st.empty()
            progress_bar = st.progress(0)
            status_container.info("⏳ Subiendo e indexando documento...")
            time.sleep(1.5)
            progress_bar.progress(100)
            status_container.success("✓ Documento procesado correctamente.")
            st.session_state.documents.insert(0, {
                "name": uploaded_file.name, # <--- Change this back to uploaded_file
                "status": "✓ Indexado",
                "date": datetime.now(timezone.utc).strftime('%d/%m/%Y'),
                "sections": 28
            })
            time.sleep(1)
            st.rerun()

    st.markdown("#### Archivos disponibles")
    for doc in st.session_state.documents:
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([4, 2, 2, 1])
            c1.markdown(f"**📄 {doc['name']}**")
            c2.markdown(f"<span style='color: #8AB4F8;'>{doc['status']}</span>", unsafe_allow_html=True)
            c3.caption(f"{doc['sections']} secciones")
            if c4.button("Eliminar", key=f"del_{doc['name']}"):
                st.session_state.documents.remove(doc)
                st.rerun()

# --- MAIN ROUTER ---
if st.session_state.view == "workspace":
    render_workspace()
elif st.session_state.view == "documents":
    render_document_management()