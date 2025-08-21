\
import streamlit as st
import pandas as pd
from streamlit_plotly_events import plotly_events
from st_aggrid import AgGrid, GridOptionsBuilder
from utils.ui import inject_fonts_and_css, kpi
from utils.data import kpis_company, peak_window_counts
from utils.charts import bar_peak, donut_service_mode, bar_top

st.set_page_config(page_title="Account Manager • Platable Insights", page_icon="🧑‍💼", layout="wide")
inject_fonts_and_css()
st.sidebar.image("assets/logo.svg", use_column_width=True)
st.title("Account Manager")

if "data_df" not in st.session_state:
    st.info("Go to **Settings** and upload your combined sheet.")
    st.stop()

df_all = st.session_state["data_df"]
ams = sorted(df_all["account_manager"].fillna("Unassigned").unique().tolist())
am = st.selectbox("Choose Account Manager", options=ams, index=0)

df = df_all.copy()
df["am_filled"] = df["account_manager"].fillna("Unassigned")
df = df[df["am_filled"]==am]

m = kpis_company(df)
c1,c2,c3,c4,c5,c6 = st.columns(6)
with c1: kpi("Managed Vendors", df["brand"].nunique())
with c2: kpi("GMV", f"AED {m['gmv']:,.2f}")
with c3: kpi("Orders", f"{m['orders']:,}")
with c4: kpi("Revenue", f"AED {m['revenue']:,.2f}")
with c5: kpi("Payout", f"AED {m['payout']:,.2f}")
with c6: kpi("AOV", f"AED {m['aov']:,.2f}")

st.write('<div class="click-hint">Click charts to drill into orders below.</div>', unsafe_allow_html=True)

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
    st.markdown("**Top vendors (Top 10 by GMV)**")
    fig_v, agg_v = bar_top(df, "brand", "GMV", 10)
    clicked_vendor = plotly_events(fig_v, click_event=True, hover_event=False, select_event=False, override_height=380, override_width="100%")
with col2:
    st.markdown("**Top items (Top 10 by GMV)**")
    fig_i, agg_i = bar_top(df, "item_name", "GMV", 10)
    clicked_item = plotly_events(fig_i, click_event=True, hover_event=False, select_event=False, override_height=380, override_width="100%")

mask = pd.Series(True, index=df.index)
if clicked_peak:
    mask &= (df["time_bucket"] == clicked_peak[0]["x"])
if clicked_donut:
    mask &= (df["service_mode"] == clicked_donut[0]["label"])
if clicked_vendor:
    mask &= (df["brand"] == clicked_vendor[0]["y"])
if clicked_item:
    mask &= (df["item_name"] == clicked_item[0]["y"])

st.markdown("### Orders (drill)")
grid_df = df[mask][["order_number","date","time","brand","store_name","item_name","service_mode","order_state","order_value","commission","pg","revenue","payout","customer","account_manager"]].copy()
gb = GridOptionsBuilder.from_dataframe(grid_df)
gb.configure_default_column(filter=True, sortable=True, resizable=True)
AgGrid(grid_df, gridOptions=gb.build(), fit_columns_on_grid_load=True)

st.markdown("### Vendors table")
vt = df.groupby("brand").agg(
    Outlets=("store_name","nunique"),
    Orders=("order_number","count"),
    GMV=("order_value","sum"),
    AOV=("order_value","mean"),
    Revenue=("revenue","sum"),
    Payout=("payout","sum"),
    PickupPct=("is_pickup","mean"),
    LastActivity=("date","max")
).reset_index()
gb2 = GridOptionsBuilder.from_dataframe(vt)
gb2.configure_default_column(filter=True, sortable=True, resizable=True)
AgGrid(vt, gridOptions=gb2.build(), fit_columns_on_grid_load=True)
