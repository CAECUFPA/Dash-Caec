import streamlit as st
import plotly.express as px
import plotly.graph_objects as go

from .base_page import BasePage
from .config import INSTITUTIONAL, PAGE_CONFIG
from .style import load_css
from .filters import apply_sidebar_filters
from .kpis import render_kpis

# Importamos a classe que centraliza todos os gráficos
from .plots import FinanceVisualizer

__all__ = [
    "st",
    "px",
    "go",
    "BasePage",
    "INSTITUTIONAL",
    "PAGE_CONFIG",
    "load_css",
    "FinanceVisualizer",  # Classe centralizadora
    "apply_sidebar_filters",
    "render_kpis",
]
