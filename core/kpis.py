import streamlit as st


def render_kpis(df):
    # Cálculos base
    receitas = df[df["VALOR_NUM"] > 0]["VALOR_NUM"].sum()
    despesas = df[df["VALOR_NUM"] < 0]["VALOR_NUM"].sum()
    saldo_real = receitas + despesas

    # Representatividade (Margem sobre Receita)
    p_saldo = (saldo_real / receitas * 100) if receitas > 0 else 0

    c1, c2, c3 = st.columns(3)

    # CARD 1: ENTRADAS (Verde)
    c1.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-label">ENTRADAS</div>
            <div class="val-receita">R$ {receitas:,.2f}</div>
            <div class="delta-box delta-up">▲ 100% <span class="delta-text">do fluxo</span></div>
        </div>
    """,
        unsafe_allow_html=True,
    )

    # CARD 2: SAÍDAS (Vermelho)
    c2.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-label">SAÍDAS</div>
            <div class="val-despesa">R$ {abs(despesas):,.2f}</div>
            <div class="delta-box delta-down">▼ {abs(despesas) / receitas * 100 if receitas > 0 else 0:.1f}% <span class="delta-text">consumo</span></div>
        </div>
    """,
        unsafe_allow_html=True,
    )

    # CARD 3: SALDO LÍQUIDO (Azul e Seta Corrigida)
    # Definimos a seta e a cor do badge (delta) baseada no saldo,
    # mas o valor principal R$ será sempre azul.
    seta_simbolo = "▲" if saldo_real >= 0 else "▼"
    classe_delta = "delta-up" if saldo_real >= 0 else "delta-down"

    c3.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-label">SALDO LÍQUIDO</div>
            <div class="val-saldo">R$ {saldo_real:,.2f}</div>
            <div class="delta-box {classe_delta}">
                {seta_simbolo} {abs(p_saldo):.1f}% <span class="delta-text">de margem</span>
            </div>
        </div>
    """,
        unsafe_allow_html=True,
    )
