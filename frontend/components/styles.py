# File: frontend/components/styles.py

import streamlit as st

def apply_fichaclara_theme():
    st.markdown("""
        <style>
        /* Typography */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');
        html, body, [class*="css"] {
            font-family: 'Inter', sans-serif;
        }
        
        :root {
            --primary-blue: #155EEF;
            --medical-teal: #0F9D8A;
            --bg-surface: #FFFFFF;
            --bg-app: #F8FAFC;
        }
        
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        
        /* Source Card Styling */
        .source-card {
            background-color: var(--bg-surface);
            border-left: 4px solid var(--medical-teal);
            padding: 1rem;
            margin-bottom: 1rem;
            border-radius: 4px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        
        .pii-warning {
            background-color: #FEF3C7;
            border-left: 4px solid #D97706;
            color: #92400E;
            padding: 1rem;
            border-radius: 4px;
        }
        
        /* --- GEMINI-STYLE SIDEBAR NAVIGATION --- */
        [data-testid="stSidebar"] button {
            justify-content: flex-start !important;
            text-align: left !important;
            border-radius: 8px !important;
            padding: 0.5rem 1rem !important;
            border: none !important;
            box-shadow: none !important;
            transition: background-color 0.2s ease;
        }
        
        [data-testid="stSidebar"] button[kind="secondary"] {
            background-color: transparent !important;
            color: #172033 !important;
            font-weight: 500 !important;
        }
        
        [data-testid="stSidebar"] button[kind="secondary"]:hover {
            background-color: #F1F5F9 !important;
        }
        
        [data-testid="stSidebar"] button[kind="primary"] {
            background-color: #EFF6FF !important;
            color: #155EEF !important;
            font-weight: 600 !important;
        }
        
        /* --- CHAT INPUT STYLING --- */
        [data-testid="stChatInput"] {
            padding-bottom: 20px !important;
        }
        
        .stChatInputContainer {
            border-radius: 20px !important;
            border: 1px solid #E2E8F0 !important;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05) !important;
        }

        /* --- CLEAN POPOVER ICON (No fixed positioning) --- */
        button[data-testid="stPopoverButton"] {
            background-color: transparent !important;
            border: none !important;
            box-shadow: none !important;
            padding: 0.5rem !important;
        }
        
        /* Hide the dropdown arrow completely */
        button[data-testid="stPopoverButton"] div[aria-hidden="true"],
        button[data-testid="stPopoverButton"] svg {
            display: none !important;
        }
        
        
        button[data-testid="stPopoverButton"]:hover {
            opacity: 0.7 !important;
            background-color: transparent !important;
        }
        </style>
    """, unsafe_allow_html=True)