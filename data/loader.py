import gspread
import pandas as pd
import streamlit as st
from oauth2client.service_account import ServiceAccountCredentials
from typing import Tuple, List

EXPECTED_COLS = [
    "DATA",
    "TIPO",
    "CATEGORIA",
    "DESCRIÇÃO",
    "VALOR",
    "OBSERVAÇÃO",
    "SALDO",
]


def get_gspread_client():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds_dict = dict(st.secrets["google_sheets"])
    creds_dict["private_key"] = creds_dict["private_key"].replace("\\n", "\n")
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scopes)
    return gspread.authorize(creds)


def parse_money(val) -> float:
    if pd.isna(val) or val == "":
        return 0.0
    s = (
        str(val)
        .strip()
        .replace("R$", "")
        .replace(".", "")
        .replace(",", ".")
        .replace(" ", "")
    )
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s.strip("()")
    try:
        return float(s)
    except:  # noqa: E722
        return 0.0 


def process_data_logic(values: List[List[str]]) -> Tuple[pd.DataFrame, bool]:
    if not values or len(values) < 2:
        return pd.DataFrame(columns=EXPECTED_COLS), False

    header = [str(h).strip() for h in values[1]]
    mismatch = not all(col in header for col in EXPECTED_COLS)
    df = pd.DataFrame(values[2:], columns=header if not mismatch else None)

    if mismatch:
        df = pd.DataFrame(values[2:]).iloc[:, : len(EXPECTED_COLS)]
        df.columns = EXPECTED_COLS

    df["DATA"] = pd.to_datetime(df["DATA"], dayfirst=True, errors="coerce")
    df = df.dropna(subset=["DATA"]).copy()
    df["VALOR_NUM"] = df["VALOR"].apply(parse_money)

    for col in ["TIPO", "CATEGORIA", "DESCRIÇÃO", "OBSERVAÇÃO"]:
        df[col] = df[col].fillna("N/D").astype(str).str.strip().replace("", "N/D")

    # LOGICA DE SINAL: Despesa fica negativa (-) e Receita positiva (+)
    mask_despesa = df["TIPO"].str.contains("Despesa", case=False)
    df.loc[mask_despesa, "VALOR_NUM"] = -df.loc[mask_despesa, "VALOR_NUM"].abs()

    mask_receita = df["TIPO"].str.contains("Receita", case=False)
    df.loc[mask_receita, "VALOR_NUM"] = df.loc[mask_receita, "VALOR_NUM"].abs()

    df = df.sort_values("DATA").reset_index(drop=True)
    df["Saldo Acumulado"] = df["VALOR_NUM"].cumsum()
    df["year_month"] = df["DATA"].dt.to_period("M").astype(str)

    return df, mismatch


@st.cache_data(ttl=600)
def load_and_preprocess_data() -> Tuple[pd.DataFrame, bool]:
    try:
        client = get_gspread_client()
        sh = client.open(st.secrets["SPREADSHEET_NAME"])
        ws = sh.get_worksheet(int(st.secrets.get("WORKSHEET_INDEX", 0)))
        return process_data_logic(ws.get_all_values())
    except Exception as e:
        st.error(f"Erro ao carregar: {e}")
        return pd.DataFrame(columns=EXPECTED_COLS), False
