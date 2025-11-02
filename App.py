# app.py
"""
Dashboard Financeiro Caec — Versão final com identidade visual completa,
tema adaptativo, tipografia oficial, KPIs com delta (últimos 30 dias) e gráfico percentual.
Logo esperada: ./logo.png
"""

from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
import os

import numpy as np
import pandas as pd
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

# Optional libs for Google Sheets if configured
try:
    import gspread
    from oauth2client.service_account import ServiceAccountCredentials
    GS_AVAILABLE = True
except Exception:
    GS_AVAILABLE = False

# ========= CONFIGURAÇÃO VISUAL (PALETA & FONTS) =========
PALETA = {
    "azul": "#042b51",
    "amarelo": "#f6d138",
    "branco": "#ffffff",
    "preto": "#231f20",
    "receita": "#1fa34a",  # verde
    "despesa": "#dc2626",  # vermelho
    "saldo": "#1f67b4",    # azul destaque para saldo
    "neutral": "#6c757d"
}

# Background SVG (textura leve — treliça / blueprint)
BACKGROUND_SVG = (
    "data:image/svg+xml;utf8,"
    "<svg xmlns='http://www.w3.org/2000/svg' width='200' height='200' viewBox='0 0 200 200'>"
    "<defs><pattern id='p' width='40' height='40' patternUnits='userSpaceOnUse'>"
    "<path d='M0 20 L40 20 M20 0 L20 40' stroke='%23042251' stroke-opacity='0.04' stroke-width='1'/>"
    "<path d='M0 0 L40 40 M40 0 L0 40' stroke='%23231f20' stroke-opacity='0.02' stroke-width='0.5'/>"
    "</pattern></defs><rect width='200' height='200' fill='url(%23p)' /></svg>"
)

# ========= CSS & FONTES =========
# Usamos Google Fonts Anton, League Spartan, Open Sans
GLOBAL_CSS = f"""
<link href="https://fonts.googleapis.com/css2?family=Anton&family=League+Spartan:wght@600;700&family=Open+Sans:wght@400;600&display=swap" rel="stylesheet">
<style>
:root {{
  --caec-azul: {PALETA['azul']};
  --caec-amarelo: {PALETA['amarelo']};
  --caec-branco: {PALETA['branco']};
  --caec-preto: {PALETA['preto']};
  --caec-receita: {PALETA['receita']};
  --caec-despesa: {PALETA['despesa']};
  --caec-saldo: {PALETA['saldo']};
  --caec-neutral: {PALETA['neutral']};
}}
/* Page background & fonts */
body .stApp {{
  background-image: url("{BACKGROUND_SVG}");
  background-repeat: repeat;
  background-attachment: fixed;
  font-family: "Open Sans", sans-serif;
}}
h1, .title-main {{
  font-family: 'Anton', sans-serif;
  color: var(--caec-azul);
}}
h2, .subtitle {{
  font-family: 'League Spartan', sans-serif;
  color: var(--caec-azul);
}}
.kpi-card {{
  background: rgba(255,255,255,0.92);
  border-radius: 12px;
  padding: 12px 14px;
  box-shadow: 0 4px 10px rgba(2,6,23,0.06);
}}
.kpi-label {{ font-family: 'League Spartan', sans-serif; color: var(--caec-azul); font-size:0.9rem; }}
.kpi-value {{ font-family: 'Anton', sans-serif; font-size:1.4rem; }}
.kpi-delta {{ font-size:0.85rem; color:#475569; }}
.small-muted {{ color: #6b7280; font-size:0.85rem; }}
.header-row {{ display:flex; align-items:center; gap:12px; }}
.logo-img {{ border-radius:6px; }}
.footer {{ text-align:center; color:#94a3b8; padding-top:10px; font-size:0.85rem; }}
/* Adaptations for dark mode override (when chosen) */
body.dark-mode .kpi-card {{ background: rgba(6,11,26,0.75); border: 1px solid rgba(255,255,255,0.03); }}
</style>
"""
st.set_page_config(page_title="Dashboard Financeiro CAEC", layout="wide", initial_sidebar_state="expanded",
                   menu_items={"About": "CAEC — Dashboard Financeiro — Deusa Atenas © 2025"})
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

# ========= UTILITÁRIOS =========

EXPECTED_COLS = ["DATA", "TIPO", "CATEGORIA", "DESCRIÇÃO", "VALOR", "OBSERVAÇÃO"]

def parse_val_str_to_float(val) -> float:
    if pd.isna(val) or val == "":
        return 0.0
    s = str(val).strip()
    neg = False
    if (s.startswith("(") and s.endswith(")")) or s.startswith("-"):
        neg = True
        s = s.strip("()-")
    s = s.replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
    try:
        n = float(s)
    except Exception:
        return 0.0
    return -abs(n) if neg else abs(n)

def money_fmt_br(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# ========= CARREGAMENTO DE DADOS =========
# Prioridade:
# 1) Google Sheets via st.secrets (se disponível)
# 2) data.csv in project root
# 3) dataset de exemplo (para testes)

@st.cache_resource(ttl=600)
def get_gspread_client() -> Optional[object]:
    if not GS_AVAILABLE:
        return None
    try:
        creds = st.secrets["gcp_service_account"]
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_obj = ServiceAccountCredentials.from_json_keyfile_dict(creds, scopes)
        client = gspread.authorize(creds_obj)
        return client
    except Exception:
        return None

def load_sheet_values(client) -> List[List[str]]:
    try:
        sh_name = st.secrets["SPREADSHEET_NAME"]
        ws_index = int(st.secrets.get("WORKSHEET_INDEX", 0))
        sh = client.open(sh_name)
        ws = sh.get_worksheet(ws_index)
        return ws.get_all_values()
    except Exception:
        return []

def build_dataframe_from_sheet(values: List[List[str]]) -> Tuple[pd.DataFrame, bool]:
    if not values or len(values) < 2:
        return pd.DataFrame(columns=EXPECTED_COLS), False
    header = [str(x).strip() for x in values[1]]
    body = values[2:] if len(values) > 2 else []
    if all(col in header for col in EXPECTED_COLS):
        df = pd.DataFrame(body, columns=header)[EXPECTED_COLS].copy()
        return df, False
    # fallback: try to pad rows to EXPECTED_COLS
    max_len = max((len(r) for r in body), default=0)
    target_len = max(max_len, len(EXPECTED_COLS))
    padded = [r + [""]*(target_len - len(r)) for r in body]
    if padded:
        df = pd.DataFrame(padded, columns=EXPECTED_COLS)
    else:
        df = pd.DataFrame(columns=EXPECTED_COLS)
    return df, True

def load_data() -> Tuple[pd.DataFrame, bool]:
    # 1) try google sheets
    client = get_gspread_client()
    if client:
        vals = load_sheet_values(client)
        if vals:
            df, header_mismatch = build_dataframe_from_sheet(vals)
            return df, header_mismatch
    # 2) try local CSV
    if os.path.exists("data.csv"):
        try:
            df = pd.read_csv("data.csv")
            # ensure expected cols if possible
            missing = [c for c in EXPECTED_COLS if c not in df.columns]
            if missing:
                # attempt to adapt if columns lowercase
                df.columns = [c.upper() for c in df.columns]
            df = df[[c for c in EXPECTED_COLS if c in df.columns]]
            return df, False
        except Exception:
            pass
    # 3) example synthetic dataset for demo
    today = pd.Timestamp(datetime.now().date())
    rng = pd.date_range(end=today, periods=120, freq='D')
    receita = np.random.randint(400, 3000, size=len(rng))
    despesa = np.random.randint(300, 2500, size=len(rng))
    rows = []
    cats = ["Material", "Serviços", "Salários", "Infra", "Outros"]
    for d, r, p in zip(rng, receita, despesa):
        # one revenue
        rows.append([d.strftime("%d/%m/%Y"), "Receita", np.random.choice(cats), "Venda/Serviço", f"R$ {r:,.2f}", ""])
        # one expense (negative)
        rows.append([d.strftime("%d/%m/%Y"), "Despesa", np.random.choice(cats), "Despesa", f"R$ {p:,.2f}", ""])
    df = pd.DataFrame(rows, columns=EXPECTED_COLS)
    return df, False

# ========= PREPROCESSAMENTO =========

def preprocess_df(df_raw: pd.DataFrame) -> pd.DataFrame:
    df = df_raw.copy()
    # standardize columns
    df.columns = [c.upper() for c in df.columns]
    for col in EXPECTED_COLS:
        if col not in df.columns:
            df[col] = ""
    df["DATA"] = pd.to_datetime(df["DATA"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["DATA"]).reset_index(drop=True)
    df["VALOR"] = df["VALOR"].astype(str)
    df["VALOR_NUM"] = df["VALOR"].apply(parse_val_str_to_float)
    df["TIPO"] = df["TIPO"].fillna("").astype(str).str.strip()
    mask_empty = df["TIPO"] == ""
    df.loc[mask_empty, "TIPO"] = df.loc[mask_empty, "VALOR_NUM"].apply(lambda x: "Despesa" if x < 0 else "Receita")
    m_rec = df["TIPO"].str.contains("Receita", case=False, na=False)
    m_dep = df["TIPO"].str.contains("Despesa", case=False, na=False)
    df.loc[m_rec, "VALOR_NUM"] = abs(df.loc[m_rec, "VALOR_NUM"])
    df.loc[m_dep, "VALOR_NUM"] = -abs(df.loc[m_dep, "VALOR_NUM"])
    df["CATEGORIA"] = df["CATEGORIA"].fillna("NÃO CATEGORIZADO").astype(str).str.strip()
    df["DESCRIÇÃO"] = df["DESCRIÇÃO"].fillna("N/D").astype(str)
    df["OBSERVAÇÃO"] = df["OBSERVAÇÃO"].fillna("N/D").astype(str)
    df = df.sort_values("DATA").reset_index(drop=True)
    df["Saldo Acumulado"] = df["VALOR_NUM"].cumsum()
    df["year_month"] = df["DATA"].dt.to_period("M").astype(str)
    return df

# ========= KPI / DELTA (30 dias) =========

def sum_period(df: pd.DataFrame, start_dt: pd.Timestamp, end_dt: pd.Timestamp, tipo: str="all") -> float:
    if df.empty:
        return 0.0
    mask = (df["DATA"] >= start_dt) & (df["DATA"] <= end_dt)
    s = df.loc[mask, "VALOR_NUM"]
    if tipo == "receita":
        return s[s > 0].sum()
    if tipo == "despesa":
        return s[s < 0].sum()  # negative
    return s.sum()

def kpi_delta(curr: float, prev: float, positive_is_good: bool=True) -> Tuple[str, str]:
    """
    Return: (formatted_delta_text, 'up'|'down'|'neutral')
    For despesas we pass magnitudes (positive numbers) and positive_is_good=False.
    """
    diff = curr - prev
    # Avoid division by zero: if prev==0 and diff !=0 treat as 100% growth (or -100 if decreased)
    if abs(prev) < 1e-9:
        pct = 100.0 if abs(diff) > 0 else 0.0
    else:
        pct = (diff / abs(prev)) * 100.0
    sign = "+" if diff >= 0 else "-"
    txt = f"{sign}{money_fmt_br(abs(diff))} ({sign}{abs(pct):.0f}%)"
    if abs(diff) < 1e-6:
        direction = "neutral"
    else:
        increased = diff > 0
        if increased:
            direction = "up" if positive_is_good else "down"
        else:
            direction = "down" if positive_is_good else "up"
    return txt, direction

# ========= UI RENDER: KPIs (HTML cards) =========

def render_header_with_logo():
    cols = st.columns([0.12, 0.88])
    with cols[0]:
        if os.path.exists("logo.png"):
            st.image("logo.png", width=110, caption=None, output_format="PNG")
        else:
            # fallback simple SVG stylized Athena column
            st.markdown(f"<div style='width:110px;height:64px;border-radius:6px;background:{PALETA['azul']};display:flex;align-items:center;justify-content:center;color:{PALETA['branco']};font-weight:700;'>CAEC</div>", unsafe_allow_html=True)
    with cols[1]:
        st.markdown("<div class='header-row'><div><h1 class='title-main'>Deusa Atenas — Centro Acadêmico de Engenharia Civil</h1><div class='small-muted'>Dashboard Financeiro — Identidade CAEC</div></div></div>", unsafe_allow_html=True)

def render_kpis_and_summary(df: pd.DataFrame):
    if df.empty:
        st.info("Sem dados para exibir KPIs.")
        return

    # last available day in dataset (use as anchor)
    last_date = df["DATA"].max()
    # last 30 days window: inclusive of last_date and 29 previous days (30 days total)
    last30_end = pd.to_datetime(last_date)
    last30_start = last30_end - pd.Timedelta(days=29)
    prev30_end = last30_start - pd.Timedelta(seconds=1)
    prev30_start = prev30_end - pd.Timedelta(days=29)

    # totals (global/filtered)
    receita_total = df.loc[df["VALOR_NUM"] > 0, "VALOR_NUM"].sum()
    despesa_total = df.loc[df["VALOR_NUM"] < 0, "VALOR_NUM"].sum()  # negative
    saldo_total = receita_total + despesa_total

    # period sums for delta
    receita_curr = sum_period(df, last30_start, last30_end, tipo="receita")
    receita_prev = sum_period(df, prev30_start, prev30_end, tipo="receita")
    despesa_curr = -sum_period(df, last30_start, last30_end, tipo="despesa")  # convert to magnitude
    despesa_prev = -sum_period(df, prev30_start, prev30_end, tipo="despesa")
    saldo_curr = receita_curr - despesa_curr
    saldo_prev = receita_prev - despesa_prev

    # compute deltas
    txt_rec_delta, dir_rec = kpi_delta(receita_curr, receita_prev, positive_is_good=True)
    txt_dep_delta, dir_dep = kpi_delta(despesa_curr, despesa_prev, positive_is_good=False)
    txt_saldo_delta, dir_saldo = kpi_delta(saldo_curr, saldo_prev, positive_is_good=True)

    # Render three KPI cards
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("<div class='kpi-card'>", unsafe_allow_html=True)
        st.markdown(f"<div class='kpi-label'>Receita — Total</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='kpi-value' style='color:{PALETA['receita']};'>{money_fmt_br(receita_total)}</div>", unsafe_allow_html=True)
        # delta block (last 30)
        arrow = "▲" if dir_rec == "up" else ("▼" if dir_rec == "down" else "—")
        color = PALETA['receita'] if dir_rec == "up" else (PALETA['despesa'] if dir_rec == "down" else "#6b7280")
        st.markdown(f"<div class='kpi-delta' style='color:{color};'>{arrow} {txt_rec_delta} <span class='small-muted'> (últimos 30d)</span></div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with c2:
        st.markdown("<div class='kpi-card'>", unsafe_allow_html=True)
        st.markdown(f"<div class='kpi-label'>Despesa — Total</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='kpi-value' style='color:{PALETA['despesa']};'>{money_fmt_br(abs(despesa_total))}</div>", unsafe_allow_html=True)
        arrow = "▲" if dir_dep == "up" else ("▼" if dir_dep == "down" else "—")
        color = PALETA['despesa'] if dir_dep == "up" else (PALETA['receita'] if dir_dep == "down" else "#6b7280")
        st.markdown(f"<div class='kpi-delta' style='color:{color};'>{arrow} {txt_dep_delta} <span class='small-muted'> (últimos 30d)</span></div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with c3:
        st.markdown("<div class='kpi-card'>", unsafe_allow_html=True)
        st.markdown(f"<div class='kpi-label'>Saldo — Atual</div>", unsafe_allow_html=True)
        st.markdown(f"<div class='kpi-value' style='color:{PALETA['saldo']};'>{money_fmt_br(saldo_total)}</div>", unsafe_allow_html=True)
        arrow = "▲" if dir_saldo == "up" else ("▼" if dir_saldo == "down" else "—")
        color = PALETA['saldo'] if dir_saldo == "up" else (PALETA['despesa'] if dir_saldo == "down" else "#6b7280")
        st.markdown(f"<div class='kpi-delta' style='color:{color};'>{arrow} {txt_saldo_delta} <span class='small-muted'> (últimos 30d)</span></div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # small note about period
    st.markdown(f"<div class='small-muted'>Período de comparação: {last30_start.date()} → {last30_end.date()}  vs  {prev30_start.date()} → {prev30_end.date()}</div>", unsafe_allow_html=True)

    return {
        "receita_total": receita_total,
        "despesa_total": despesa_total,
        "saldo_total": saldo_total,
        "receita_curr": receita_curr,
        "despesa_curr": despesa_curr,
        "saldo_curr": saldo_curr
    }

# ========= GRÁFICOS =========

def plot_percent_bar(revenue: float, expense: float):
    """
    Substitui o donut: mostra proporção Receita vs Despesa em barras percentuais.
    Receitas e Despesas são comparadas por magnitude (abs).
    """
    rev = max(0.0, float(revenue))
    exp = max(0.0, float(expense))
    total_flow = rev + exp if (rev + exp) > 0 else 1.0
    rev_pct = rev / total_flow * 100.0
    exp_pct = exp / total_flow * 100.0

    dfp = pd.DataFrame({
        "Categoria": ["Receita", "Despesa"],
        "Valor": [rev, exp],
        "Percent": [rev_pct, exp_pct]
    })

    fig = px.bar(dfp, x="Percent", y="Categoria", orientation='h', text="Percent",
                 color="Categoria", color_discrete_map={"Receita": PALETA['receita'], "Despesa": PALETA['despesa']})
    fig.update_traces(texttemplate='%{text:.1f}%', textposition='inside', insidetextanchor='middle')
    fig.update_layout(height=280, margin=dict(l=20, r=20, t=20, b=20),
                      xaxis=dict(range=[0,100], title="Percentual (%)"),
                      yaxis=dict(title=""), showlegend=False,
                      plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
    return fig

def plot_saldo_evolucao(df: pd.DataFrame):
    if df.empty:
        fig = go.Figure()
        fig.add_annotation(text="Sem dados", xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
        return fig
    daily = df.groupby(df["DATA"].dt.date)["Saldo Acumulado"].last().reset_index()
    daily["DATA"] = pd.to_datetime(daily["DATA"])
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=daily["DATA"], y=daily["Saldo Acumulado"], mode="lines+markers", name="Saldo", line=dict(color=PALETA['saldo'], width=2)))
    fig.update_layout(height=360, margin=dict(t=20, b=20, l=20, r=20), plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
    fig.update_xaxes(title_text="Data")
    fig.update_yaxes(title_text="Saldo (R$)")
    return fig

def plot_fluxo_diario(df: pd.DataFrame):
    if df.empty:
        return go.Figure()
    fluxo = df.groupby(df["DATA"].dt.date)["VALOR_NUM"].sum().reset_index()
    fluxo["DATA"] = pd.to_datetime(fluxo["DATA"])
    cores = [PALETA['receita'] if v >= 0 else PALETA['despesa'] for v in fluxo["VALOR_NUM"]]
    fig = go.Figure(go.Bar(x=fluxo["DATA"], y=fluxo["VALOR_NUM"], marker_color=cores))
    fig.update_layout(height=320, margin=dict(t=20,b=20,l=20,r=20), plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)')
    fig.update_xaxes(title_text="Data")
    fig.update_yaxes(title_text="Valor (R$)")
    return fig

# ========= SIDEBAR (THEME & FILTROS) =========

def sidebar_controls(df: pd.DataFrame) -> Dict:
    st.sidebar.title("Controles — CAEC")
    theme_choice = st.sidebar.radio("Tema (Auto/Manual)", options=["Auto", "Light", "Dark"], index=0)
    st.sidebar.markdown("---")

    # date filters
    min_d = df["DATA"].min().date() if not df.empty else datetime.now().date() - timedelta(days=365)
    max_d = df["DATA"].max().date() if not df.empty else datetime.now().date()
    date_range = st.sidebar.date_input("Período (início → fim)", value=(min_d, max_d), min_value=min_d, max_value=max_d)
    selected_categories = st.sidebar.multiselect("Categorias (filtrar)", options=sorted(df["CATEGORIA"].unique()), default=None)
    st.sidebar.markdown("---")
    if st.sidebar.button("Limpar cache & recarregar"):
        try:
            st.cache_data.clear()
            st.cache_resource.clear()
            st.sidebar.success("Cache limpo — recarregue a página.")
        except Exception:
            st.sidebar.warning("Falha ao limpar cache (ambiente).")

    return {"theme": theme_choice, "date_range": date_range, "categories": selected_categories}

# ========= APLICAR FILTROS =========

def apply_filters(df: pd.DataFrame, controls: Dict) -> pd.DataFrame:
    f = df.copy()
    dr = controls["date_range"]
    if isinstance(dr, (list, tuple)) and len(dr) == 2:
        start = pd.to_datetime(dr[0])
        end = pd.to_datetime(dr[1]) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        f = f[(f["DATA"] >= start) & (f["DATA"] <= end)]
    cats = controls["categories"]
    if cats:
        f = f[f["CATEGORIA"].isin(cats)]
    return f.reset_index(drop=True)

# ========= MAIN =========

def main():
    # Header + logo
    st.markdown("<div style='padding-top:6px'></div>", unsafe_allow_html=True)
    render_header_with_logo()

    # Load raw data
    raw_df, header_mismatch = load_data()
    df = preprocess_df(raw_df)

    # Sidebar controls
    controls = sidebar_controls(df)

    # Theme handling: apply dark-mode class to body if Dark selected
    theme = controls["theme"]
    if theme == "Dark":
        st.markdown("<script>document.body.classList.add('dark-mode');</script>", unsafe_allow_html=True)
        # tune some CSS for dark background
        st.markdown(f"<style>body{{background-color: #071226; color: {PALETA['branco']};}} .stApp{{background-color:#071226;}}</style>", unsafe_allow_html=True)
    elif theme == "Light":
        st.markdown("<script>document.body.classList.remove('dark-mode');</script>", unsafe_allow_html=True)
        st.markdown(f"<style>body{{background-color: {PALETA['branco']}; color: {PALETA['preto']};}} .stApp{{background-color:{PALETA['branco']};}}</style>", unsafe_allow_html=True)
    else:
        # Auto: attempt to detect streamlit theme option (best-effort); if not possible, keep light
        try:
            base = st.get_option("theme.base")
            if base == "dark":
                st.markdown("<script>document.body.classList.add('dark-mode');</script>", unsafe_allow_html=True)
            else:
                st.markdown("<script>document.body.classList.remove('dark-mode');</script>", unsafe_allow_html=True)
        except Exception:
            pass

    # Apply filters to df
    df_filtered = apply_filters(df, controls)

    # Warning if header mismatch
    if header_mismatch:
        st.warning("Cabeçalho da planilha (linha 2) difere do esperado; dados carregados com tentativa de adaptação.")

    # KPIs (totals + deltas)
    summary = render_kpis_and_summary(df_filtered)

    st.markdown("---")

    # Layout: left column for percent bar + saldo evolution; right column for daily flux and table
    col_left, col_right = st.columns([0.55, 0.45])

    with col_left:
        st.subheader("Fluxo — Proporção Receita vs Despesa")
        fig_pct = plot_percent_bar(summary["receita_curr"], summary["despesa_curr"])
        st.plotly_chart(fig_pct, use_container_width=True, config={"displayModeBar": False})

        st.subheader("Evolução do Saldo")
        st.plotly_chart(plot_saldo_evolucao(df_filtered), use_container_width=True, config={"displayModeBar": False})

    with col_right:
        st.subheader("Fluxo Diário (soma por dia)")
        st.plotly_chart(plot_fluxo_diario(df_filtered), use_container_width=True, config={"displayModeBar": False})
        st.markdown("---")
        st.subheader("Lançamentos Recentes")
        recent = df_filtered.sort_values("DATA", ascending=False).head(12)
        if recent.empty:
            st.info("Sem lançamentos no período filtrado.")
        else:
            # show compact table
            recent_display = recent.copy()
            recent_display["Data"] = recent_display["DATA"].dt.strftime("%Y-%m-%d")
            recent_display["Valor"] = recent_display["VALOR_NUM"].apply(money_fmt_br)
            st.dataframe(recent_display[["Data", "TIPO", "CATEGORIA", "DESCRIÇÃO", "Valor"]], use_container_width=True)

    # Export CSV button
    csv_bytes = df_filtered.to_csv(index=False).encode("utf-8-sig")
    st.download_button("Exportar (CSV) — Filtro atual", data=csv_bytes, file_name="caec_export.csv", mime="text/csv")

    st.markdown("---")
    st.markdown("<div class='footer'>CAEC © 2025 — Centro Acadêmico de Engenharia Civil — Desenvolvido por Rick</div>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()
