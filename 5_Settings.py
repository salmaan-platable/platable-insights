\
import io
import json
import streamlit as st
import pandas as pd
from utils.ui import inject_fonts_and_css
from utils.data import transform

st.set_page_config(page_title="Settings • Platable Insights", page_icon="⚙️", layout="wide")
inject_fonts_and_css()
st.sidebar.image("assets/logo.svg", use_column_width=True)
st.title("Settings")

st.markdown("Upload your **combined orders** sheet (XLSX/CSV). We’ll use your `Revenue` and `Payout` columns directly.")

up = st.file_uploader("Upload file", type=["xlsx","csv"])
with st.expander("Impact parameters (optional)"):
    params = st.session_state.get("impact_params", {
        "avg_order_weight_kg": 0.40,
        "kg_per_meal": 0.40,
        "co2e_per_kg_food_rescued": 2.5,
        "last_mile_co2e_delivery_kg": 1.0,
        "last_mile_co2e_pickup_kg": 0.2,
        "enable_pickup_co2e_component": True
    })
    c1,c2,c3 = st.columns(3)
    with c1:
        params["avg_order_weight_kg"] = st.number_input("Avg order weight (kg)", value=float(params["avg_order_weight_kg"]), step=0.05, min_value=0.0)
        params["kg_per_meal"] = st.number_input("kg per meal", value=float(params["kg_per_meal"]), step=0.05, min_value=0.1)
    with c2:
        params["co2e_per_kg_food_rescued"] = st.number_input("CO₂e per kg rescued", value=float(params["co2e_per_kg_food_rescued"]), step=0.1, min_value=0.0)
        params["last_mile_co2e_delivery_kg"] = st.number_input("Last-mile CO₂e (delivery)", value=float(params["last_mile_co2e_delivery_kg"]), step=0.1, min_value=0.0)
    with c3:
        params["last_mile_co2e_pickup_kg"] = st.number_input("Last-mile CO₂e (pickup)", value=float(params["last_mile_co2e_pickup_kg"]), step=0.1, min_value=0.0)
        params["enable_pickup_co2e_component"] = st.checkbox("Add pickup CO₂e component", value=bool(params["enable_pickup_co2e_component"]))
    st.session_state["impact_params"] = params

if up is not None:
    try:
        if up.name.lower().endswith(".xlsx"):
            import openpyxl
            raw = pd.read_excel(up, engine="openpyxl")
        else:
            raw = pd.read_csv(up)
        st.success(f"Loaded {len(raw):,} rows • {len(raw.columns)} columns")
        st.write("Schema preview:", pd.DataFrame({"Column": raw.columns.astype(str)}))
        data_df = transform(raw, st.session_state["impact_params"])
        st.session_state["data_df"] = data_df
        st.write("Transformed preview:", data_df.head(30))
        st.success("Data is ready. Open any view from the sidebar.")
    except Exception as e:
        st.error(f"Failed to read file: {e}")

st.caption("Note: Cancelled orders are excluded from KPIs & charts by default but remain visible via table filters.")
