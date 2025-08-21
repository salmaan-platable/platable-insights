\
import streamlit as st
import pandas as pd
from streamlit_plotly_events import plotly_events
from st_aggrid import AgGrid, GridOptionsBuilder
from utils.ui import inject_fonts_and_css, kpi
from utils.data import transform, kpis_company, peak_window_counts
from utils.charts import bar_peak, donut_service_mode, bar_top

st.set_page_config(page_title="Company • Platable Insights", page_icon="🏢", layout="wide")
inject_fonts_and_css()
st.sidebar.image("assets/logo.svg", use_column_width=True)
st.title("Company")

if "data_df" not in st.session_state:
    st.info("Go to **Settings** and upload your combined sheet (XLSX/CSV).")
    st.stop()

df = st.session_state["data_df"]

# KPIs
m = kpis_company(df)
c1,c2,c3,c4,c5,c6 = st.columns(6)
with c1: kpi("GMV", f"AED {m['gmv']:,.2f}")
with c2: kpi("Revenue", f"AED {m['revenue']:,.2f}")
with c3: kpi("Payout", f"AED {m['payout']:,.2f}")
with c4: kpi("Orders", f"{m['orders']:,}")
with c5: kpi("AOV", f"AED {m['aov']:,.2f}")
with c6: kpi("Items Sold", f"{m['items_sold']:,}")
c1,c2,c3,c4,c5,c6 = st.columns(6)
with c1: kpi("Unique Items", m['u_items'])
with c2: kpi("Unique Vendors", m['u_vendors'])
with c3: kpi("Unique Outlets", m['u_outlets'])
with c4: kpi("Unique Customers", m['u_customers'])
with c5: kpi("Repeat %", f"{m['repeat_pct']*100:.1f}%")
with c6: kpi("Pickup Share %", f"{m['pickup_share']*100:.1f}%")
c1,c2,c3 = st.columns(3)
with c1: kpi("Food Rescued (kg)", f"{m['food_kg']:,.1f}")
with c2: kpi("Meals Equivalent", f"{m['meals']:,.1f}")
with c3: kpi("CO₂e Avoided (kg)", f"{m['co2']:,.1f}" if m['co2'] else "0.0")
if m.get("pickup_co2", 0) > 0:
    st.caption(f"Pickup CO₂e Avoided component: **{m['pickup_co2']:,.2f} kg**")

st.write('<div class="click-hint">Click any chart to show matching orders below. Tables have column filters & sorting.</div>', unsafe_allow_html=True)

# Charts row
col1, col2 = st.columns([1.1, 0.9])
with col1:
    st.markdown("**Peak window (by Orders)**")
    pk = peak_window_counts(df, value="orders")
    fig_peak = bar_peak(pk, "orders")
    clicked_peak = plotly_events(fig_peak, click_event=True, hover_event=False, select_event=False, override_height=360, override_width="100%")
with col2:
    st.markdown("**Pickup vs Delivery**")
    fig_donut = donut_service_mode(df)
    clicked_donut = plotly_events(fig_donut, click_event=True, hover_event=False, select_event=False, override_height=320, override_width="100%")

col1, col2 = st.columns(2)
with col1:
    st.markdown("**Top 10 brands by GMV**")
    fig_b, agg_b = bar_top(df, "brand", "GMV", 10)
    clicked_brand = plotly_events(fig_b, click_event=True, hover_event=False, select_event=False, override_height=380, override_width="100%")
with col2:
    st.markdown("**Top 10 outlets by Orders**")
    fig_o, agg_o = bar_top(df, "store_name", "Orders", 10)
    clicked_outlet = plotly_events(fig_o, click_event=True, hover_event=False, select_event=False, override_height=380, override_width="100%")

col1, col2 = st.columns(2)
with col1:
    st.markdown("**Top 10 items by Items Sold**")
    fig_i, agg_i = bar_top(df, "item_name", "Items", 10)
    clicked_item = plotly_events(fig_i, click_event=True, hover_event=False, select_event=False, override_height=380, override_width="100%")
with col2:
    st.empty()

# Drill logic
mask = pd.Series(True, index=df.index)

if clicked_peak:
    buck = clicked_peak[0]["x"]
    mask &= (df["time_bucket"] == buck)

if clicked_donut:
    seg = clicked_donut[0]["label"]
    mask &= (df["service_mode"] == seg)

if clicked_brand:
    sel = clicked_brand[0]["y"]
    mask &= (df["brand"] == sel)

if clicked_outlet:
    sel = clicked_outlet[0]["y"]
    mask &= (df["store_name"] == sel)

if clicked_item:
    sel = clicked_item[0]["y"]
    mask &= (df["item_name"] == sel)

st.markdown("### Orders (drill)")
grid_df = df[mask][["order_number","date","time","brand","store_name","item_name","service_mode","order_state","order_value","commission","pg","revenue","payout","customer","account_manager"]].copy()
gb = GridOptionsBuilder.from_dataframe(grid_df)
gb.configure_default_column(filter=True, sortable=True, resizable=True)
AgGrid(grid_df, gridOptions=gb.build(), fit_columns_on_grid_load=True)
