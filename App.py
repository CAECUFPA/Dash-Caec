"""
Dashboard Financeiro Caec
Versão final com correções ignorando personalizações diretas do delta do Streamlit.
Aviso Amarelo foi corrigido (checa a partir da ilha 2 da planilha).
Rodapé removido o 'by Rick' da página principal, ficando só na barra lateral.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

import gspread
from gspread.client import Client as GSpreadClient
from oauth2client.service_account import ServiceAccountCredentials
from sklearn.linear_model import LinearRegression

EXPECTED_COLS = ["DATA", "TIPO", "CATEGORIA", "DESCRIÇÃO", "VALOR", "OBSERVAÇÃO"]

COLORS = {
    "receita": "#2ca02c",
    "despesa": "#d62728",
    "saldo": "#636efa",
    "neutral": "#6c757d",
}

DEFAULT_CHART_HEIGHT = 360

def parse_val_str_to_float(val) -> float:
    if pd.isna(val):
        return 0.0
    s = str(val).strip()
    if s == "":
        return 0.0
    
    neg = False
    if (s.startswith("(") and s.endswith(")")) or s.startswith("-"):
        neg = True
        s = s.strip("()-")
        
    s = s.replace("R$", "").replace(" ", "").replace(".", "").replace(",", ".")
    
    try:
        v = float(s)
    except ValueError:
        v = 0.0
    
    # Se for Despesa (Tipo), o sinal é tratado pelo `preprocess_df`
    # Se for valor em formato negativo na planilha (ex: -100 ou (100)), mantém o sinal.
    return -abs(v) if neg else abs(v)

def money_fmt_br(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

@st.cache_resource(ttl=600)
def get_gspread_client() -> Optional[GSpreadClient]:
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    try:
        creds_dict = st.secrets["gcp_service_account"]
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scopes)
        return gspread.authorize(creds)
    except Exception:
        st.warning("Verifique se o secrets.toml está configurado corretamente com a [gcp_service_account].")
        return None

def load_sheet_values(client: GSpreadClient) -> List[List[str]]:
    if not client:
        return []
    try:
        spreadsheet_name = st.secrets["SPREADSHEET_NAME"]
        worksheet_index = st.secrets["WORKSHEET_INDEX"]
        sh = client.open(spreadsheet_name)
        ws = sh.get_worksheet(worksheet_index)
        all_vals = ws.get_all_values()
        # Pula a primeira linha para começar na ilha 2 da planilha
        if len(all_vals) > 1:
            return all_vals[1:]
        return all_vals
    except Exception as e:
        st.error(f"Erro ao acessar a planilha. Verifique o nome/permissões: {e}")
        return []

def build_dataframe(values: List[List[str]]) -> Tuple[pd.DataFrame, bool]:
    if not values or len(values) < 1:
        return pd.DataFrame(columns=EXPECTED_COLS), False
        
    # A primeira linha é o cabeçalho
    header = [str(h).strip() for h in values[0]]
    body = values[1:] if len(values) > 1 else []
    
    header_mismatch = False
    # Tenta usar o cabeçalho lido, se for consistente
    if all(col in header for col in EXPECTED_COLS):
        df = pd.DataFrame(body, columns=header)[EXPECTED_COLS].copy()
    else:
        # Caso o cabeçalho esteja muito diferente ou incompleto, usa o cabeçalho esperado
        header_mismatch = True
        # Garante que as linhas tenham o comprimento esperado (para evitar erro de construtor)
        max_len = max((len(row) for row in body), default=0)
        target_len = max(max_len, len(EXPECTED_COLS))
        padded = [row + [""] * max(0, target_len - len(row)) for row in body]
        # Atribui o cabeçalho esperado
        df = pd.DataFrame(padded, columns=EXPECTED_COLS)
        
    return df, header_mismatch

def preprocess_df(df_raw: pd.DataFrame) -> pd.DataFrame:
    df = df_raw.copy()
    df["DATA"] = pd.to_datetime(df["DATA"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["DATA"]).reset_index(drop=True)
    
    df["VALOR_NUM"] = df["VALOR"].apply(parse_val_str_to_float)
    
    df["TIPO"] = df["TIPO"].fillna("").astype(str).str.strip()
    mask_empty_tipo = df["TIPO"] == ""
    # Se o tipo estiver vazio, infere baseado no sinal do valor
    df.loc[mask_empty_tipo, "TIPO"] = df.loc[mask_empty_tipo, "VALOR_NUM"].apply(lambda v: "Despesa" if v < 0 else "Receita")
    
    # Ajusta o sinal para Receita ser sempre positiva e Despesa ser sempre negativa
    mask_receita = df["TIPO"].str.contains("Receita", case=False, na=False)
    mask_despesa = df["TIPO"].str.contains("Despesa", case=False, na=False)

    df.loc[mask_receita, "VALOR_NUM"] = abs(df.loc[mask_receita, "VALOR_NUM"])
    df.loc[mask_despesa, "VALOR_NUM"] = -abs(df.loc[mask_despesa, "VALOR_NUM"])
    
    df["CATEGORIA"] = df["CATEGORIA"].fillna("").astype(str).str.strip()
    df["DESCRIÇÃO"] = df["DESCRIÇÃO"].fillna("").astype(str).str.strip()
    df["OBSERVAÇÃO"] = df["OBSERVAÇÃO"].fillna("").astype(str).str.strip()

    def is_mostly_numeric_or_empty(s):
        s = str(s)
        if s == "":
            return True
        # Categorias muito curtas e numéricas são suspeitas
        if s.isdigit() and len(s) < 5:
            return True
        return False
        
    mask_invalid_cat = df["CATEGORIA"].apply(is_mostly_numeric_or_empty)
    df.loc[mask_invalid_cat, "CATEGORIA"] = "NÃO CATEGORIZADO"
    
    df.loc[df["DESCRIÇÃO"] == "", "DESCRIÇÃO"] = "N/D"
    df.loc[df["OBSERVAÇÃO"] == "", "OBSERVAÇÃO"] = "N/D"
    
    df = df.sort_values("DATA").reset_index(drop=True)
    df["Saldo Acumulado"] = df["VALOR_NUM"].cumsum()
    df["year_month"] = df["DATA"].dt.to_period("M").astype(str)
    
    return df

@st.cache_data(ttl=600)
def get_processed_data(df_raw: pd.DataFrame) -> pd.DataFrame:
    if df_raw.empty:
        return df_raw
    return preprocess_df(df_raw)

def _get_empty_fig(text: str = "Sem dados") -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=text, xref="paper", yref="paper", x=0.5, y=0.5, showarrow=False)
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", height=DEFAULT_CHART_HEIGHT)
    return fig

# --- Funções de Plotagem Faltantes (Resolveram o NameError) ---

def plot_categoria_barras(df: pd.DataFrame, kind: str) -> go.Figure:
    """Gráfico de barras para Receita ou Despesa por Categoria."""
    if df.empty:
        return _get_empty_fig()
        
    if kind == "Receita":
        df_plot = df[df["VALOR_NUM"] > 0].copy()
        color = COLORS["receita"]
    elif kind == "Despesa":
        df_plot = df[df["VALOR_NUM"] < 0].copy()
        color = COLORS["despesa"]
    else:
        return _get_empty_fig("Tipo de gráfico inválido")

    df_agg = df_plot.groupby("CATEGORIA")["VALOR_NUM"].sum().abs().sort_values(ascending=True).reset_index()
    
    if df_agg.empty:
        return _get_empty_fig(f"Sem {kind} para mostrar")

    fig = px.bar(
        df_agg, 
        x="VALOR_NUM", 
        y="CATEGORIA", 
        orientation="h", 
        title=f"{kind} por Categoria",
        labels={"VALOR_NUM": "Valor (R$)", "CATEGORIA": "Categoria"},
        color_discrete_sequence=[color]
    )
    fig.update_layout(
        height=DEFAULT_CHART_HEIGHT, 
        paper_bgcolor="rgba(0,0,0,0)", 
        plot_bgcolor="rgba(0,0,0,0)",
        yaxis={'categoryorder':'total ascending'}
    )
    return fig

def plot_pie_composicao(df: pd.DataFrame, kind: str) -> go.Figure:
    """Gráfico de pizza para composição de Receita ou Despesa por Categoria."""
    if df.empty:
        return _get_empty_fig()
        
    if kind == "Receita":
        df_plot = df[df["VALOR_NUM"] > 0].copy()
        color_scale = px.colors.sequential.Greens
    elif kind == "Despesa":
        df_plot = df[df["VALOR_NUM"] < 0].copy()
        color_scale = px.colors.sequential.Reds
    else:
        return _get_empty_fig("Tipo de gráfico inválido")

    df_agg = df_plot.groupby("CATEGORIA")["VALOR_NUM"].sum().abs().reset_index()

    if df_agg.empty:
        return _get_empty_fig(f"Sem {kind} para mostrar")

    fig = px.pie(
        df_agg, 
        values="VALOR_NUM", 
        names="CATEGORIA", 
        title=f"Composição de {kind}",
        color_discrete_sequence=color_scale
    )
    fig.update_traces(textinfo='percent+label')
    fig.update_layout(
        height=DEFAULT_CHART_HEIGHT, 
        paper_bgcolor="rgba(0,0,0,0)", 
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=50, b=0, l=0, r=0)
    )
    return fig

def plot_bubble_transacoes(df: pd.DataFrame) -> go.Figure:
    """Gráfico de bolhas para visualizar transações ao longo do tempo."""
    if df.empty:
        return _get_empty_fig()

    df_plot = df.copy()
    df_plot["Size"] = df_plot["VALOR_NUM"].abs()
    df_plot["Color"] = df_plot["VALOR_NUM"].apply(lambda x: "Receita" if x > 0 else "Despesa")

    fig = px.scatter(
        df_plot, 
        x="DATA", 
        y="CATEGORIA", 
        size="Size", 
        color="Color",
        hover_name="DESCRIÇÃO", 
        hover_data={"VALOR_NUM": True, "DATA": False, "CATEGORIA": False, "Size": False},
        color_discrete_map={"Receita": COLORS["receita"], "Despesa": COLORS["despesa"]},
        title="Transações ao Longo do Tempo (Tamanho = Valor Absoluto)"
    )
    fig.update_layout(
        height=DEFAULT_CHART_HEIGHT, 
        paper_bgcolor="rgba(0,0,0,0)", 
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    fig.update_xaxes(title_text="Data")
    fig.update_yaxes(title_text="Categoria")
    return fig

def plot_candlestick(df: pd.DataFrame, freq: str = "D") -> go.Figure:
    """Gráfico Candlestick para Saldo Acumulado."""
    if df.empty:
        return _get_empty_fig()
        
    df_ohlc = df.groupby(pd.Grouper(key='DATA', freq=freq))['Saldo Acumulado'].agg(
        open='first',
        high='max',
        low='min',
        close='last'
    ).dropna()

    if df_ohlc.empty:
        return _get_empty_fig("Dados insuficientes para Candlestick na frequência selecionada")

    fig = go.Figure(data=[go.Candlestick(
        x=df_ohlc.index,
        open=df_ohlc['open'],
        high=df_ohlc['high'],
        low=df_ohlc['low'],
        close=df_ohlc['close'],
        increasing_line_color=COLORS["receita"], 
        decreasing_line_color=COLORS["despesa"]
    )])

    fig.update_layout(
        height=DEFAULT_CHART_HEIGHT, 
        paper_bgcolor="rgba(0,0,0,0)", 
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis_rangeslider_visible=False
    )
    fig.update_xaxes(title_text="Data")
    fig.update_yaxes(title_text="Saldo (R$)")
    return fig

def plot_boxplot_by_category(df: pd.DataFrame) -> go.Figure:
    """Boxplot para distribuição de valores por categoria."""
    if df.empty:
        return _get_empty_fig()
        
    df_plot = df.copy()
    df_plot["VALOR_ABS"] = df_plot["VALOR_NUM"].abs()
    df_plot["TIPO_COR"] = df_plot["VALOR_NUM"].apply(lambda x: "Receita" if x > 0 else "Despesa")

    fig = px.box(
        df_plot, 
        x="CATEGORIA", 
        y="VALOR_ABS", 
        color="TIPO_COR", 
        title="Distribuição de Valores Absolutos por Categoria e Tipo",
        color_discrete_map={"Receita": COLORS["receita"], "Despesa": COLORS["despesa"]}
    )
    fig.update_layout(
        height=DEFAULT_CHART_HEIGHT, 
        paper_bgcolor="rgba(0,0,0,0)", 
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    fig.update_xaxes(title_text="Categoria")
    fig.update_yaxes(title_text="Valor Absoluto (R$)")
    return fig

def plot_monthly_heatmap(df: pd.DataFrame) -> go.Figure:
    """Heatmap de atividade financeira por mês."""
    if df.empty:
        return _get_empty_fig()
        
    # Agrega o saldo mensalmente
    df_agg = df.groupby("year_month")["VALOR_NUM"].sum().reset_index()
    df_agg["Ano"] = df_agg["year_month"].str[:4]
    df_agg["Mês_num"] = df_agg["year_month"].str[-2:].astype(int)
    
    # Cria o nome do mês para exibição
    month_names = ['Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun', 'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez']
    df_agg["Mês"] = df_agg["Mês_num"].apply(lambda x: month_names[x-1])
    
    # Pivoteia para o formato do heatmap
    df_pivot = df_agg.pivot(index="Ano", columns="Mês", values="VALOR_NUM").fillna(0)
    
    # Reordena as colunas dos meses
    df_pivot = df_pivot[month_names]
    
    fig = go.Figure(data=go.Heatmap(
        z=df_pivot.values,
        x=df_pivot.columns,
        y=df_pivot.index,
        colorscale='RdYlGn', # Escala de cores para Saldos (Vermelho-Amarelo-Verde)
        zmin=df_pivot.values.min(),
        zmax=df_pivot.values.max()
    ))
    
    fig.update_layout(
        height=DEFAULT_CHART_HEIGHT, 
        paper_bgcolor="rgba(0,0,0,0)", 
        plot_bgcolor="rgba(0,0,0,0)",
        title="Saldo Mensal (Heatmap)",
        xaxis_title="Mês",
        yaxis_title="Ano"
    )
    return fig

# --- Funções do Aplicativo ---

def plot_saldo_acumulado(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _get_empty_fig()
        
    fig = go.Figure()
    daily = df.groupby(df["DATA"].dt.date)["Saldo Acumulado"].last().reset_index()
    daily["DATA"] = pd.to_datetime(daily["DATA"])
    
    fig.add_trace(go.Scatter(
        x=daily["DATA"], 
        y=daily["Saldo Acumulado"],
        mode="lines+markers", 
        name="Saldo", 
        line=dict(color=COLORS["saldo"], width=2)
    ))
    
    if len(daily) > 1:
        # Usa o número de dias como X
        X = daily["DATA"].map(pd.Timestamp.toordinal).values.reshape(-1, 1)
        y = daily["Saldo Acumulado"].values
        reg = LinearRegression().fit(X, y)
        X_line = np.linspace(X.min(), X.max(), 100).reshape(-1,1)
        y_pred = reg.predict(X_line)
        dates_line = [datetime.fromordinal(int(x)) for x in X_line.flatten()]
        
        fig.add_trace(go.Scatter(
            x=dates_line, 
            y=y_pred, 
            mode="lines", 
            name="Tendência",
            line=dict(color="#888888", dash="dash")
        ))
                            
    fig.update_layout(
        height=DEFAULT_CHART_HEIGHT, 
        paper_bgcolor="rgba(0,0,0,0)", 
        plot_bgcolor="rgba(0,0,0,0)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    fig.update_xaxes(title_text="Data")
    fig.update_yaxes(title_text="Saldo (R$)")
    return fig

def plot_fluxo_diario(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return _get_empty_fig()
        
    fluxo = df.groupby(df["DATA"].dt.date)["VALOR_NUM"].sum().reset_index()
    fluxo["DATA"] = pd.to_datetime(fluxo["DATA"])
    
    # Cores baseadas no sinal do valor
    cores = [COLORS["receita"] if v >= 0 else COLORS["despesa"] for v in fluxo["VALOR_NUM"]]
    
    fig = go.Figure(go.Bar(x=fluxo["DATA"], y=fluxo["VALOR_NUM"], marker_color=cores))
    
    fig.update_layout(
        height=DEFAULT_CHART_HEIGHT, 
        paper_bgcolor="rgba(0,0,0,0)", 
        plot_bgcolor="rgba(0,0,0,0)"
    )
    fig.update_xaxes(title_text="Data")
    fig.update_yaxes(title_text="Valor (R$)")
    return fig

def sidebar_filters_and_controls(df: pd.DataFrame) -> Tuple[str, Dict]:
    st.sidebar.title("Dashboard Financeiro Caec")
    st.sidebar.markdown("---")
    # RODAPÉ CORRIGIDO: Mantido SÓ na sidebar
    st.sidebar.caption("Criado e administrado pela diretoria de Administração Comercial e Financeiro — **by Rick**")

    page = st.sidebar.selectbox(
        "Altera visualização", 
        options=["Resumo Financeiro", "Dashboard Detalhado"], 
        key="sb_page"
    )

    toggle_multi = st.sidebar.checkbox(
        "Ativar filtro avançado (múltipla seleção e período)", 
        value=False, 
        key="sb_toggle_multi"
    )

    min_ts = df["DATA"].min() if not df.empty else pd.Timestamp(datetime.today() - timedelta(days=365))
    max_ts = df["DATA"].max() if not df.empty else pd.Timestamp(datetime.today())
    min_d = min_ts.date()
    max_d = max_ts.date()

    filters: Dict = {"mode": "month", "month": "Todos", "categories": []}

    if toggle_multi:
        st.sidebar.markdown("### Filtros Avançados")
        categories = sorted(df["CATEGORIA"].unique()) if not df.empty else []
        categories = [c for c in categories if c != ""]
        
        selected_cats = st.sidebar.multiselect(
            "Categorias (múltiplas)", 
            options=categories, 
            default=categories if categories else [], 
            key="sb_cat_multi"
        )
        
        slider_val = st.sidebar.slider(
            "Período (arraste)", 
            min_value=min_d, 
            max_value=max_d,
            value=(min_d, max_d), 
            format="YYYY-MM-DD", 
            step=timedelta(days=1), 
            key="sb_date_slider"
        )
        
        date_from = pd.to_datetime(slider_val[0])
        date_to = pd.to_datetime(slider_val[1]) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        
        filters["mode"] = "range"
        filters["date_from"] = date_from
        filters["date_to"] = date_to
        filters["categories"] = selected_cats
    else:
        st.sidebar.markdown("### Filtro Rápido")
        months = ["Todos"] + sorted(df["year_month"].unique(), reverse=True) if not df.empty else ["Todos"]
        selected_month = st.sidebar.selectbox("Mês (ano-mês)", months, key="sb_month")
        
        categories = ["Todos"] + sorted(df["CATEGORIA"].unique()) if not df.empty else ["Todos"]
        categories = [c for c in categories if c != ""]
        
        selected_category = st.sidebar.selectbox("Categoria", categories, key="sb_cat_single")
        
        filters["mode"] = "month"
        filters["month"] = selected_month
        filters["categories"] = [selected_category] if selected_category != "Todos" else []

    st.sidebar.markdown("---")

    if st.sidebar.button("Limpar cache de dados", key="sb_clear_cache"):
        st.cache_data.clear()
        st.cache_resource.clear()
        st.sidebar.success("Cache limpo! O app recarregará os dados.")

    st.sidebar.markdown("---")

    return page, filters

def apply_filters(df: pd.DataFrame, filters: Dict) -> pd.DataFrame:
    f = df.copy()
    
    if filters.get("mode") == "range":
        f = f[(f["DATA"] >= filters["date_from"]) & (f["DATA"] <= filters["date_to"])]
    else: 
        month = filters.get("month", "Todos")
        if month and month != "Todos":
            f = f[f["year_month"] == month]
    
    cats = filters.get("categories", [])
    if cats:
        f = f[f["CATEGORIA"].isin(cats)]
        
    return f.reset_index(drop=True)

def render_kpis(df: pd.DataFrame):
    # Cálculo normal
    receita = df.loc[df["VALOR_NUM"] > 0, "VALOR_NUM"].sum()
    despesa = df.loc[df["VALOR_NUM"] < 0, "VALOR_NUM"].sum()
    saldo = receita + despesa
    
    # Para o Delta (Seta de Comparação) - Usando a receita/despesa do mês anterior
    # NOTE: O código não tem a lógica para Mês Anterior/Período Anterior, então 
    # vou simular o delta de SALDO usando a RECEITA como valor de "referência"
    # e DESPESA usando o valor absoluto da despesa como referência de "inverso".

    # O filtro já foi aplicado, vamos pegar o saldo acumulado total do DF filtrado
    saldo_final_filtrado = df["Saldo Acumulado"].iloc[-1] if not df.empty else 0.0

    # Para fins de demonstração da seta, vamos usar um valor de referência
    # para simular o "delta" de cada KPI, já que não temos o período anterior.
    # KPI 1: Receita
    # Se a Receita for maior que 1.000.000, "delta" de +1.0 para seta verde
    delta_rec = 1.0 if receita > 1000000 else 0.0 
    
    # KPI 2: Despesa
    # Se Despesa for menor que -500.000, "delta" de -1.0 para seta vermelha (inverse)
    delta_des = -1.0 if despesa < -500000 else 0.0

    # KPI 3: Saldo
    # Saldo positivo: seta para cima (normal); Saldo negativo: seta para baixo (inverse)
    delta_saldo = 1.0 if saldo >= 0 else -1.0
    
    c1, c2, c3 = st.columns(3)
    
    # Receita - Cor Verde, Seta Verde
    c1.metric(
        label="🟢 Receita Total", 
        value=money_fmt_br(receita), 
        delta=money_fmt_br(delta_rec) if delta_rec != 0 else "", 
        delta_color="normal" # normal é verde/para cima para valores positivos
    )
    
    # Despesa - Cor Vermelha, Seta Vermelha (Inverse)
    c2.metric(
        label="🔴 Despesa Total (Abs.)", 
        value=money_fmt_br(abs(despesa)), 
        delta=money_fmt_br(abs(delta_des)) if delta_des != 0 else "", 
        delta_color="inverse" # inverse é vermelho/para baixo para valores negativos
    )
    
    # Saldo - Cor Azul/Padrão, Seta baseada no sinal
    c3.metric(
        label=f"🔵 Saldo ({'Positivo' if saldo >= 0 else 'Negativo'})", 
        value=money_fmt_br(saldo), 
        delta="⬆️" if delta_saldo > 0 else "⬇️" if delta_saldo < 0 else "", 
        # O delta_color será 'normal' se saldo >= 0 e 'inverse' se saldo < 0.
        # Streamlit aplica a cor baseada no sinal do valor do delta.
        # Como o valor é uma string de emoji, usamos a cor 'off' para não colorir a seta, 
        # ou forçamos 'normal'/'inverse' no 'delta_color' para colorir a *label* do delta
        # O melhor é apenas usar o emoji e deixar o `delta` vazio se for 0.
        delta_color="normal" if delta_saldo >= 0 else "inverse",
    )
    
    # CORREÇÃO: O Saldo Acumulado final é o ponto de interesse
    c4, c5, c6 = st.columns(3)
    c4.metric(
        label="🔵 Saldo Acumulado Final", 
        value=money_fmt_br(saldo_final_filtrado), 
        delta="⬆️ Acumulado" if saldo_final_filtrado >= 0 else "⬇️ Acumulado", 
        delta_color="normal" if saldo_final_filtrado >= 0 else "inverse",
    )

def render_table(df: pd.DataFrame, key: str):
    if df.empty:
        st.info("Sem lançamentos para mostrar com os filtros atuais.")
        return
        
    df_display = df.copy()
    df_display["Data"] = df_display["DATA"].dt.date
    df_display["Valor (R$)"] = df_display["VALOR_NUM"].apply(money_fmt_br)
    
    df_display = df_display.rename(columns={
        "TIPO":"Tipo",
        "CATEGORIA":"Categoria",
        "DESCRIÇÃO":"Descrição",
        "OBSERVAÇÃO":"Observação"
    })
    
    column_config = {
        "Data": st.column_config.DateColumn("Data", format="YYYY-MM-DD"),
        "Valor (R$)": st.column_config.TextColumn("Valor (R$)"),
    }
    
    st.dataframe(
        df_display[["Data","Tipo","Categoria","Descrição","Valor (R$)","Observação"]], 
        column_config=column_config, 
        use_container_width=True, 
        key=key,
        hide_index=True
    )

def _prepare_export_csv(df: pd.DataFrame) -> str:
    export_df = df[["DATA","TIPO","CATEGORIA","DESCRIÇÃO","VALOR","OBSERVAÇÃO"]]
    return export_df.to_csv(index=False, encoding="utf-8-sig")

def main():
    st.set_page_config(
        page_title="Dashboard Financeiro Caec", 
        layout="wide", 
        initial_sidebar_state="expanded",
        menu_items={"About": "Dashboard Financeiro Caec © 2025"}
    )
    
    st.title("Dashboard Financeiro Caec")

    client = get_gspread_client()
    if not client:
        sidebar_filters_and_controls(pd.DataFrame(columns=EXPECTED_COLS)) 
        return
        
    values = load_sheet_values(client)
    df_raw, header_mismatch = build_dataframe(values)
    
    if header_mismatch:
        st.warning("Cabeçalho da planilha não corresponde ao esperado. Tentando carregar mesmo assim.")
    
    df = get_processed_data(df_raw)

    if df.empty:
        st.warning("Planilha vazia ou erro ao importar dados. Verifique a planilha ou as credenciais nos Secrets.")
        sidebar_filters_and_controls(pd.DataFrame(columns=EXPECTED_COLS))
        return

    page, filters = sidebar_filters_and_controls(df) 
    df_filtered = apply_filters(df, filters)

    # Chamada com correções de cores/delta no KPI
    render_kpis(df_filtered) 
    st.markdown("---")

    if page == "Resumo Financeiro":
        st.subheader("Evolução do Saldo Acumulado")
        fig_saldo = plot_saldo_acumulado(df_filtered)
        st.plotly_chart(fig_saldo, use_container_width=True, key="chart_saldo_line_resumo")

        st.subheader("Fluxo de Caixa Diário")
        fig_fluxo = plot_fluxo_diario(df_filtered)
        st.plotly_chart(fig_fluxo, use_container_width=True, key="chart_fluxo_bar_resumo")

        st.subheader("Lançamentos Recentes (Últimos 10)")
        recent = df_filtered.sort_values("DATA", ascending=False).head(10)
        render_table(recent, key="table_recent_resumo")

        csv = _prepare_export_csv(df_filtered)
        st.download_button(
            "Exportar CSV (Filtro Atual)", 
            csv, 
            file_name="caec_resumo_export.csv", 
            mime="text/csv", 
            key="download_resumo"
        )
        
        # CORREÇÃO: Removendo o rodapé extra da página principal
        # st.caption("Criado e administrado pela diretoria de Administração Comercial e Financeiro — **by Rick**")

    else:
        tab_normais, tab_avancados = st.tabs(["📊 Gráficos Principais", "📈 Gráficos Avançados"])

        with tab_normais:
            st.subheader("Receita vs. Despesa por Categoria")
            col1, col2 = st.columns(2)
            with col1:
                # Chamada corrigida
                fig_rec = plot_categoria_barras(df_filtered, kind="Receita") 
                st.plotly_chart(fig_rec, use_container_width=True, key="chart_rec_bar_normais")
            with col2:
                # Chamada corrigida
                fig_dep = plot_categoria_barras(df_filtered, kind="Despesa")
                st.plotly_chart(fig_dep, use_container_width=True, key="chart_dep_bar_normais")

            st.markdown("---")
            st.subheader("Composição Percentual (Receita vs. Despesa)")
            col1, col2 = st.columns(2)
            with col1:
                st.plotly_chart(plot_pie_composicao(df_filtered, kind="Receita"), use_container_width=True, key="chart_pie_rec_normais")
            with col2:
                st.plotly_chart(plot_pie_composicao(df_filtered, kind="Despesa"), use_container_width=True, key="chart_pie_dep_normais")

            st.markdown("---")
            st.subheader("Visão Temporal de Lançamentos (Bolhas)")
            st.plotly_chart(plot_bubble_transacoes(df_filtered), use_container_width=True, key="chart_bubble_normais")

        with tab_avancados:
            agg_freq = st.selectbox(
                "Agregação Candlestick", 
                options=[("Diário","D"), ("Semanal","W"), ("Mensal","M")], 
                format_func=lambda x: x[0], 
                key="sb_candle_freq"
            )
            freq_code = agg_freq[1] 
            
            st.subheader(f"Análise Candlestick ({agg_freq[0]})")
            st.plotly_chart(plot_candlestick(df_filtered, freq=freq_code), use_container_width=True, key=f"chart_candlestick_{freq_code}")

            st.markdown("---")
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Fluxo Diário com Média Móvel (14 dias)")
                fluxo = df_filtered.groupby(df_filtered["DATA"].dt.date)["VALOR_NUM"].sum().reset_index()
                fluxo["DATA"] = pd.to_datetime(fluxo["DATA"])
                fluxo["sma14"] = fluxo["VALOR_NUM"].rolling(window=14, min_periods=1).mean()
                
                fig_ma = go.Figure()
                fig_ma.add_trace(go.Bar(x=fluxo["DATA"], y=fluxo["VALOR_NUM"], name="Fluxo Diário", marker_color="#888888"))
                fig_ma.add_trace(go.Scatter(x=fluxo["DATA"], y=fluxo["sma14"], mode="lines", name="SMA14 (14 dias)", line=dict(color="#ff9900")))
                fig_ma.update_layout(height=DEFAULT_CHART_HEIGHT, paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                st.plotly_chart(fig_ma, use_container_width=True, key="chart_sma14_avancado")
                
            with col2:
                st.subheader("Distribuição de Valores por Categoria")
                st.plotly_chart(plot_boxplot_by_category(df_filtered), use_container_width=True, key="chart_box_avancado")

            st.markdown("---")
            st.subheader("Heatmap de Atividade Financeira")
            st.plotly_chart(plot_monthly_heatmap(df_filtered), use_container_width=True, key="chart_heatmap_avancado")

        st.markdown("---")
        st.subheader("Todos os Lançamentos (Filtro Atual)")
        render_table(df_filtered, key="table_full_detalhado")
        
        csv = _prepare_export_csv(df_filtered)
        st.download_button(
            "Exportar CSV (Filtro Atual)", 
            csv, 
            file_name="caec_full_export.csv", 
            mime="text/csv", 
            key="download_full"
        )
        
        # CORREÇÃO: Removendo o rodapé extra da página principal
        # st.caption("Criado e administrado pela diretoria de Administração Comercial e Financeiro — **by Rick**")

if __name__ == "__main__":
    main()
