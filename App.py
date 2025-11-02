"""
Dashboard Financeiro Caec — Versão FINAL #8: Fix Mobile, UI/UX Reforçado e Boas-vindas Animado.
Foco: Visibilidade dos cards no dark mode, responsividade mobile, e harmonia visual.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from sklearn.linear_model import LinearRegression

# Google Sheets dependencies
try:
    import gspread
    from gspread.client import Client as GSpreadClient
    from oauth2client.service_account import ServiceAccountCredentials
except ImportError:
    # Mock classes for testing
    class GSpreadClient: pass
    class ServiceAccountCredentials:
        @staticmethod
        def from_json_keyfile_dict(a, b): return None

# -------------------- CONFIGURAÇÃO GERAL --------------------
EXPECTED_COLS = ["DATA", "TIPO", "CATEGORIA", "DESCRIÇÃO", "VALOR", "OBSERVAÇÃO"]

INSTITUTIONAL = {"azul": "#042b51", "amarelo": "#f6d138"}
COLORS = {"receita": "#2ca02c", "despesa": "#d62728", "saldo": "#1f77b4", "trend": INSTITUTIONAL["amarelo"], "neutral": "#6c757d"}

DEFAULT_CHART_HEIGHT = 360

BLUEPRINT_BACKGROUND_CSS = """
  background-image:
    linear-gradient(0deg, var(--bg-line-color) 1px, transparent 1px),
    linear-gradient(90deg, var(--bg-line-color) 1px, transparent 1px);
  background-size: 20px 20px;
  background-position: -1px -1px;
"""

def get_dynamic_css() -> str:
    css_vars = f"""
    @import url('https://fonts.googleapis.com/css2?family=Anton&family=Six+Caps&family=League+Spartan&family=Open+Sans:wght@400;700&display=swap');

    :root {{
      --caec-azul: {INSTITUTIONAL['azul']};
      --bg-line-color-light: rgba(200, 200, 200, 0.8);
      --sidebar-bg-transparent: rgba(255, 255, 255, 0.15); 
      --sidebar-border: rgba(200, 200, 200, 0.8);
      --bg-line-color: var(--bg-line-color-light);
      --card-padding: 18px; 
      --h1-color: #000000;
      --card-bg-color: var(--st-bgs2);
    }}

    @media (prefers-color-scheme: dark) {{
        :root {{
            --bg-line-color-dark: rgba(44, 54, 65, 0.8); 
            --sidebar-bg-transparent: rgba(11, 20, 26, 0.4); 
            --sidebar-border: rgba(44, 54, 65, 0.8);
            --bg-line-color: var(--bg-line-color-dark);
            --h1-color: #FFFFFF;
            --card-bg-color: var(--st-bgs2);
        }}
    }}

    @keyframes fadeIn {{
        from {{ opacity: 0; transform: translateY(-10px); }}
        to {{ opacity: 1; transform: translateY(0); }}
    }}
    .welcome-message {{
        font-family: 'League Spartan', sans-serif;
        font-size: 2.2rem;
        font-weight: 700;
        color: var(--caec-azul);
        text-align: center;
        margin-bottom: 2rem;
        animation: fadeIn 1.5s ease-out;
    }}

    .stApp {{
      background-color: var(--st-bgs1);
      color: var(--st-font-color);
      font-family: 'Open Sans', sans-serif; 
      {BLUEPRINT_BACKGROUND_CSS} 
    }}

    h1 {{ 
        margin-top: 0rem; 
        margin-bottom: 1rem; 
        color: var(--h1-color) !important;
        font-size: 2.5rem;
    }}
    h2, h3, h4 {{ font-family: 'Anton', 'League Spartan', sans-serif; color: var(--st-font-color) !important; }}

    .st-emotion-cache-1v4f50, .st-emotion-cache-1n743z1, .st-emotion-cache-1d9g9l8, .st-emotion-cache-0, .st-emotion-cache-zt5ig {{
        background: var(--card-bg-color);
        border: 1px solid var(--st-bgs3);
        border-radius: 12px; 
        padding: var(--card-padding); 
        margin-bottom: 1.5rem; 
        box-shadow: 0 4px 10px rgba(0, 0, 0, 0.15); 
        transition: all 0.2s ease-in-out;
    }}
    .st-emotion-cache-1d9g9l8 .st-emotion-cache-1d9g9l8, 
    .st-emotion-cache-0 .st-emotion-cache-0,
    .st-emotion-cache-1v4f50 .st-emotion-cache-1v4f50, 
    .st-emotion-cache-1n743z1 .st-emotion-cache-1n743z1 {{ background: transparent; border: none; padding: 0; margin-bottom: 0; box-shadow: none; }}

    .modebar, .plotly, .js-plotly-plot, .plotly-container {{ background-color: transparent !important; border-radius: 10px; }}
    .js-plotly-plot {{ overflow: hidden; }}

    @media (max-width: 600px) {{
        .st-emotion-cache-1v4f50, .st-emotion-cache-1n743z1, .st-emotion-cache-1d9g9l8, .st-emotion-cache-0, .st-emotion-cache-zt5ig {{
             padding: 10px; margin-bottom: 1rem;
        }}
        h1 {{ font-size: 1.8rem; }}
        h2, h3, h4 {{ font-size: 1.3rem; }}
        .kpi-value {{ font-size: 20px !important; }}
        .kpi-card {{ height: 100px; padding: 10px 12px; }}
        .kpi-label, .kpi-delta {{ font-size: 11px; }}
        .welcome-message {{ font-size: 1.5rem; }}
        .st-emotion-cache-1r6ftg6 {{ display: block !important; }}
        .st-emotion-cache-1d3x7py {{ width: 100% !important; margin-right: 0 !important; margin-bottom: 1.5rem; }}
    }}

    .st-emotion-cache-vk34a3, .st-emotion-cache-1cypk8n, .st-emotion-cache-1d371w8 {{ 
        background-color: var(--sidebar-bg-transparent) !important; 
        backdrop-filter: blur(12px) saturate(180%); -webkit-backdrop-filter: blur(12px) saturate(180%);
        border-right: 1px solid var(--sidebar-border) !important; 
    }}

    .kpi-card {{
      background: var(--st-bgs2); 
      border: 1px solid var(--st-bgs3);
      border-radius: 12px; 
      padding: 12px 14px;
      box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1); 
      width: 100%;
      height: 120px; 
      display: flex; 
      flex-direction: column;
      justify-content: space-between; 
      overflow: hidden; 
    }}
    .kpi-value {{ font-size: 26px; font-weight:700; }}
    footer {{ color: var(--st-font-color-weak); text-align:center; padding-top:10px; }}
    """
    return f"<style>{css_vars}</style>"

# -------------------- FUNÇÕES AUXILIARES --------------------

def parse_val_str_to_float(val) -> float:
    if pd.isna(val) or val == "": return 0.0
    s = str(val).strip()
    neg = False
    if (s.startswith("(") and s.endswith(")")) or s.startswith("-"):
        neg = True
        s = s.strip("()-")
    s = s.replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
    try: v = float(s)
    except: return 0.0
    return -abs(v) if neg else abs(v)

def money_fmt_br(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def get_category_color_map(df: pd.DataFrame) -> Dict[str, str]:
    if df is None or df.empty: return {}
    cats = sorted(df["CATEGORIA"].dropna().unique())
    base = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"]
    palette = [INSTITUTIONAL["azul"], INSTITUTIONAL["amarelo"]] + base
    colors = [palette[i % len(palette)] for i in range(len(cats))]
    return {cat: colors[i] for i, cat in enumerate(cats)}

@st.cache_resource(ttl=600)
def get_gspread_client() -> Optional[GSpreadClient]:
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    try:
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scopes)
        return gspread.authorize(creds)
    except: return None

# --- [Mantém todas as funções de carregamento, preprocessing, plots, KPIs, tabela e filtros] ---

# -------------------- MAIN --------------------

def main():
    st.markdown(get_dynamic_css(), unsafe_allow_html=True)
    if 'welcome_shown' not in st.session_state:
        st.markdown('<div class="welcome-message">Bem-vindo ao Centro Administrativo do Caec</div>', unsafe_allow_html=True)
        st.session_state['welcome_shown'] = True
    else:
        st.title("Dashboard Financeiro Caec")

    df_full, _ = load_and_preprocess_data()
    if df_full.empty:
        st.warning("Planilha vazia ou erro ao importar dados. Verifique a planilha/credenciais.")
        return

    page, filters = sidebar_filters_and_controls(df_full)
    df_filtered = apply_filters(df
