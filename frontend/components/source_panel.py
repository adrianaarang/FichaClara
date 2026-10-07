# File: frontend/components/source_panel.py

import streamlit as st

def render_source_card(source_dict):
    """
    Renders a polished source card based on the backend contract.
    """
    html = f"""
    <div class="source-card">
        <div style="font-size: 0.8rem; color: #64748B; text-transform: uppercase;">Source</div>
        <div style="font-weight: 600; color: #123B72; margin-top: 0.2rem;">{source_dict.get('medicine', 'Unknown Medicine')}</div>
        
        <div style="display: flex; gap: 1rem; margin-top: 0.5rem; font-size: 0.9rem;">
            <div><strong>Section:</strong> {source_dict.get('section', 'N/A')}</div>
            <div><strong>Page:</strong> {source_dict.get('page', 'N/A')}</div>
        </div>
        
        <div style="margin-top: 0.8rem; padding: 0.5rem; background-color: #F8FAFC; border-left: 2px solid #E2E8F0; font-size: 0.9rem; font-style: italic;">
            "{source_dict.get('fragment', '')}"
        </div>
        
        <div style="display: flex; justify-content: space-between; margin-top: 1rem; font-size: 0.8rem;">
            <span style="color: #64748B;">Revision: {source_dict.get('revision_date', 'Unknown')}</span>
            <a href="{source_dict.get('cima_url', '#')}" target="_blank" style="color: #155EEF; text-decoration: none; font-weight: 500;">
                Open official CIMA ↗
            </a>
        </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)