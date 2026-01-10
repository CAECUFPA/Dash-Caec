import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from datetime import datetime
from typing import List

# ==============================
# 1. CONFIGURAÇÃO GERAL
# ==============================

st.set_page_config(
    page_title="Dashboard Financeiro CAEC",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Cores Padrão (Flat Design)
COLORS = {
    "receita": "#28a745",  # Verde
    "despesa": "#dc3545",  # Vermelho
    "saldo": "#007bff",    # Azul
    "bg_kpi": "#f8f9fa"    # Cinza muito claro (fundo sólido)
}

# CSS Minimalista (Sem efeito Glass)
st.markdown(f"""
    <style>
    /* Estilo dos Cards de KPI */
    [data-testid="stMetric"] {{
        background-color: {COLORS['bg_kpi']};
        padding: 20px;
        border-radius: 8px;
        border-left: 6px solid #dee2e6;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }}
    /* Cores das bordas dos KPIs para identificação rápida */
    div[data-testid="stMetric"]:nth-of-type(1) {{ border-left-color: {COLORS['receita']}; }}
    div[data-testid="stMetric"]:nth-of-type(2) {{ border-left-color: {COLORS['despesa']}; }}
    div[data-testid="stMetric"]:nth-of-type(3) {{ border-left-color: {COLORS['saldo']}; }}
    
    /* Ajustes de espaçamento */
    .main .block-container {{ padding-top: 2rem; }}
    h1, h3 {{ font-weight: 700; color: #1e1e1e; }}
    </style>
""", unsafe_allow_html=True)

EXPECTED_COLS = ["DATA", "CATEGORIA", "DESCRIÇÃO", "VALOR", "OBSERVAÇÃO"]

# ==============================
# 2. UTILITÁRIOS
# ==============================

def parse_val_str_to_float(val) -> float:
    """Converte strings de moeda para float, tratando sinais e parênteses."""
    if pd.isna(val) or str(val).strip() == "":
        return 0.0
    
    s = str(val).strip()
    # Verifica se é negativo (por sinal ou parênteses)
    is_neg = False
    if s.startswith("-") or (s.startswith("(") and s.endswith(")")):
        is_neg = True
    
    # Limpa apenas os caracteres não numéricos, mantendo o ponto/vírgula
    s = s.replace("R$", "").replace("(", "").replace(")", "").replace("-", "").strip()
    
    # Ajusta formato BR (milhar com ponto, decimal com vírgula)
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
        
    try:
        v = float(s)
        return -abs(v) if is_neg else abs(v)
    except:
        return 0.0

def money_fmt_br(v: float) -> str:
    """Formata float para moeda Brasileira."""
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# ==============================
# 3. CONEXÃO GOOGLE SHEETS
# ==============================

try:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
except ImportError:
    gspread = None

@st.cache_resource
def get_gspread_client():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(st.secrets["gcp_service_account"], scopes)
        return gspread.authorize(creds)
    except:
        return None

def load_sheet_values():
    client = get_gspread_client()
    if not client: return []
    try:
        sh = client.open(st.secrets["SPREADSHEET_NAME"])
        ws = sh.get_worksheet(int(st.secrets.get("WORKSHEET_INDEX", 0)))
        return ws.get_all_values()
    except:
        return []

# ==============================
# 4. PROCESSAMENTO DE DADOS
# ==============================

def build_dataframe(values: List[List[str]]) -> pd.DataFrame:
    if not values or len(values) < 2:
        return pd.DataFrame(columns=EXPECTED_COLS)
    
    # Assume que a linha 1 (índice 1) é o cabeçalho
    header = [h.strip().upper() for h in values[1]]
    body = values[2:]
    
    df = pd.DataFrame(body, columns=header)
    
    # Garante que as colunas esperadas existam
    for col in EXPECTED_COLS:
        if col not in df.columns:
            df[col] = ""
            
    return df[EXPECTED_COLS]

def preprocess_df(df_raw: pd.DataFrame) -> pd.DataFrame:
    df = df_raw.copy()
    
    # 1. Trata Datas
    df["DATA"] = pd.to_datetime(df["DATA"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["DATA"]).sort_values("DATA").reset_index(drop=True)
    
    # 2. Trata Valores (AQUI ESTÁ A LÓGICA DE IDENTIFICAÇÃO)
    df["VALOR_NUM"] = df["VALOR"].apply(parse_val_str_to_float)
    
    # 3. Calcula Saldo Acumulado
    df["SALDO_ACUM"] = df["VALOR_NUM"].cumsum()
    
    # 4. Limpeza de textos
    for col in ["CATEGORIA", "DESCRIÇÃO", "OBSERVAÇÃO"]:
        df[col] = df[col].fillna("N/D").replace("", "N/D").astype(str).str.upper()
        
    return df

@st.cache_data(ttl=600)
def get_data():
    values = load_sheet_values()
    df_raw = build_dataframe(values)
    return preprocess_df(df_raw)

# ==============================
# 5. UI - COMPONENTES
# ==============================

def render_metrics(df: pd.DataFrame):
    # Lógica baseada no sinal do valor
    receita_total = df[df["VALOR_NUM"] > 0]["VALOR_NUM"].sum()
    despesa_total = df[df["VALOR_NUM"] < 0]["VALOR_NUM"].sum()
    saldo_final = receita_total + despesa_total
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Receitas", money_fmt_br(receita_total))
    c2.metric("Despesas", money_fmt_br(abs(despesa_total)))
    c3.metric("Saldo Líquido", money_fmt_br(saldo_final))

def render_charts(df: pd.DataFrame):
    col1, col2 = st.columns(2)
    
    with col1:
        # Fluxo de Caixa Diário
        fluxo = df.groupby(df["DATA"].dt.date)["VALOR_NUM"].sum().reset_index()
        fig_bar = go.Figure(go.Bar(
            x=fluxo["DATA"],
            y=fluxo["VALOR_NUM"],
            marker_color=[COLORS["receita"] if v >= 0 else COLORS["despesa"] for v in fluxo["VALOR_NUM"]]
        ))
        fig_bar.update_layout(
            title="Fluxo de Caixa Diário",
            template="plotly_white",
            height=350,
            margin=dict(l=20, r=20, t=50, b=20)
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    with col2:
        # Evolução do Saldo
        fig_line = go.Figure(go.Scatter(
            x=df["DATA"],
            y=df["SALDO_ACUM"],
            mode="lines+markers",
            line=dict(color=COLORS["saldo"], width=3),
            marker=dict(size=6),
            fill='tozeroy',
            fillcolor="rgba(0, 123, 255, 0.1)"
        ))
        fig_line.update_layout(
            title="Evolução do Saldo Acumulado",
            template="plotly_white",
            height=350,
            margin=dict(l=20, r=20, t=50, b=20)
        )
        st.plotly_chart(fig_line, use_container_width=True)

def render_table(df: pd.DataFrame):
    st.subheader("📋 Lançamentos Detalhados")
    df_show = df.copy()
    df_show["DATA"] = df_show["DATA"].dt.strftime('%d/%m/%Y')
    df_show["VALOR"] = df_show["VALOR_NUM"].apply(money_fmt_br)
    
    st.dataframe(
        df_show[["DATA", "CATEGORIA", "DESCRIÇÃO", "VALOR", "OBSERVAÇÃO"]],
        use_container_width=True,
        hide_index=True
    )

# ==============================
# 6. MAIN
# ==============================

def main():
    st.title("📊 Dashboard Financeiro CAEC")
    
    with st.spinner("Carregando dados da planilha..."):
        df = get_data()

    if df.empty:
        st.error("Não foi possível carregar os dados. Verifique sua conexão e st.secrets.")
        return

    # Parte Visual
    render_metrics(df)
    st.markdown("<br>", unsafe_allow_html=True)
    render_charts(df)
    st.markdown("---")
    render_table(df)

if __name__ == "__main__":
    main()
