\
import streamlit as st
from utils.ui import inject_fonts_and_css

st.set_page_config(page_title="Platable Insights", page_icon="🥡", layout="wide")
inject_fonts_and_css()

st.sidebar.image("assets/logo.svg", use_column_width=True)
st.title("Platable Insights")
st.caption("Company • Vendor • Item • Account Manager • Settings")

st.markdown("""
Use **Settings** to upload your combined orders sheet once. Then open any view from the left sidebar.
""")
