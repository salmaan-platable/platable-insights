\
import streamlit as st
import pandas as pd
from streamlit_plotly_events import plotly_events
from st_aggrid import AgGrid, GridOptionsBuilder
from utils.ui import inject_fonts_and_css, kpi
from utils.data import kpis_company, peak_window_counts
from utils.charts import bar_peak, donut_service_mode, bar_top

st.set_page_config(page_title="Item • Platable Insights", page_icon="🍱", layout="wide")
inject_fonts_and_css()
st.sidebar.image("assets/logo.svg", use_column_width=True)
st.title("Item")

if "data_df" not in st.session_state:
    st.info("Go to **Settings** and upload your combined sheet.")
    st.stop()

df_all = st.session_state["data_df"]
items = sorted(df_all["item_name"].dropna().unique().tolist())
item = st.selectbox("Choose item", options=["(All)"]+items, index=0)

df = df_all if item=="(All)" else df_all[df_all["item_name"]==item].copy()

m = kpis_company(df)
c1,c2,c3,c4,c5 = st.columns(5)
with c1: kpi("Items Sold", f"{m['items_sold']:,}")
with c2: kpi("GMV", f"AED {m['gmv']:,.2f}")
with c3: kpi("Orders", f"{m['orders']:,}")
with c4: kpi("Unique Customers", f"{m['u_customers']:,}")
with c5: kpi("AOV", f"AED {m['aov']:,.2f}")

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

st.markdown("**Vendors for this item (Top 10 by GMV)**")
fig_v, agg_v = bar_top(df, "brand", "GMV", 10)
clicked_vendor = plotly_events(fig_v, click_event=True, hover_event=False, select_event=False, override_height=380, override_width="100%")

mask = pd.Series(True, index=df.index)
if clicked_peak:
    mask &= (df["time_bucket"] == clicked_peak[0]["x"])
if clicked_donut:
    mask &= (df["service_mode"] == clicked_donut[0]["label"])
if clicked_vendor:
    mask &= (df["brand"] == clicked_vendor[0]["y"])

st.markdown("### Orders (drill)")
grid_df = df[mask][["order_number","date","time","brand","store_name","item_name","service_mode","order_state","order_value","commission","pg","revenue","payout","customer","account_manager"]].copy()
gb = GridOptionsBuilder.from_dataframe(grid_df)
gb.configure_default_column(filter=True, sortable=True, resizable=True)
AgGrid(grid_df, gridOptions=gb.build(), fit_columns_on_grid_load=True)

st.markdown("### Customers for this item")
cust = df.groupby("customer").agg(Orders=("order_number","count"), LastOrder=("date","max")).reset_index()
gb2 = GridOptionsBuilder.from_dataframe(cust)
gb2.configure_default_column(filter=True, sortable=True, resizable=True)
AgGrid(cust, gridOptions=gb2.build(), fit_columns_on_grid_load=True)
