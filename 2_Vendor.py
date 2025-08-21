\
import streamlit as st
import pandas as pd
from streamlit_plotly_events import plotly_events
from st_aggrid import AgGrid, GridOptionsBuilder
from utils.ui import inject_fonts_and_css, kpi
from utils.data import kpis_company, peak_window_counts
from utils.charts import bar_peak, donut_service_mode, bar_top

st.set_page_config(page_title="Vendor • Platable Insights", page_icon="🏬", layout="wide")
inject_fonts_and_css()
st.sidebar.image("assets/logo.svg", use_column_width=True)
st.title("Vendor")

if "data_df" not in st.session_state:
    st.info("Go to **Settings** and upload your combined sheet.")
    st.stop()

df_all = st.session_state["data_df"]

vendors = sorted(df_all["brand"].dropna().unique().tolist())
sel = st.multiselect("Vendor(s)", vendors, default=vendors)

df = df_all[df_all["brand"].isin(sel)] if sel else df_all.copy()

m = kpis_company(df)
c1,c2,c3,c4,c5,c6 = st.columns(6)
with c1: kpi("GMV", f"AED {m['gmv']:,.2f}")
with c2: kpi("Revenue", f"AED {m['revenue']:,.2f}")
with c3: kpi("Payout", f"AED {m['payout']:,.2f}")
with c4: kpi("Orders", f"{m['orders']:,}")
with c5: kpi("AOV", f"AED {m['aov']:,.2f}")
with c6: kpi("Items Sold", f"{m['items_sold']:,}")
c1,c2,c3,c4 = st.columns(4)
with c1: kpi("Unique Items", m['u_items'])
with c2: kpi("Outlets", m['u_outlets'])
with c3: kpi("Pickup %", f"{m['pickup_share']*100:.1f}%")
with c4: kpi("CO₂e (kg)", f"{m['co2']:,.1f}")

st.write('<div class="click-hint">Click charts to drill into the orders table below.</div>', unsafe_allow_html=True)

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
    st.markdown("**Top Items (Top 50) by Items Sold**")
    fig_it, agg_it = bar_top(df, "item_name", "Items", 50)
    clicked_item = plotly_events(fig_it, click_event=True, hover_event=False, select_event=False, override_height=380, override_width="100%")
with col2:
    st.markdown("**Outlets performance (by Orders)**")
    fig_out, agg_out = bar_top(df, "store_name", "Orders", 20)
    clicked_outlet = plotly_events(fig_out, click_event=True, hover_event=False, select_event=False, override_height=380, override_width="100%")

st.markdown("### Orders (drill)")
mask = pd.Series(True, index=df.index)
if clicked_peak:
    buck = clicked_peak[0]["x"]
    mask &= (df["time_bucket"] == buck)
if clicked_donut:
    seg = clicked_donut[0]["label"]
    mask &= (df["service_mode"] == seg)
if clicked_item:
    sel_i = clicked_item[0]["y"]
    mask &= (df["item_name"] == sel_i)
if clicked_outlet:
    sel_o = clicked_outlet[0]["y"]
    mask &= (df["store_name"] == sel_o)

grid_df = df[mask][["order_number","date","time","brand","store_name","item_name","service_mode","order_state","order_value","commission","pg","revenue","payout","customer","account_manager"]].copy()
gb = GridOptionsBuilder.from_dataframe(grid_df)
gb.configure_default_column(filter=True, sortable=True, resizable=True)
AgGrid(grid_df, gridOptions=gb.build(), fit_columns_on_grid_load=True)

st.markdown("### Outlets table")
ot = df.groupby("store_name").agg(
    Orders=("order_number","count"),
    GMV=("order_value","sum"),
    AOV=("order_value","mean"),
    Revenue=("revenue","sum"),
    Payout=("payout","sum"),
    PickupPct=("is_pickup","mean"),
    LastOrder=("date","max")
).reset_index()
gb2 = GridOptionsBuilder.from_dataframe(ot)
gb2.configure_default_column(filter=True, sortable=True, resizable=True)
AgGrid(ot, gridOptions=gb2.build(), fit_columns_on_grid_load=True)

st.markdown("### Items table (Top 50)")
it = df.groupby("item_name").agg(
    ItemsSold=("qty","sum"),
    GMV=("order_value","sum"),
    Orders=("order_number","count"),
    AOV=("order_value","mean")
).reset_index().sort_values("ItemsSold", ascending=False).head(50)
gb3 = GridOptionsBuilder.from_dataframe(it)
gb3.configure_default_column(filter=True, sortable=True, resizable=True)
AgGrid(it, gridOptions=gb3.build(), fit_columns_on_grid_load=True)

st.markdown("### Customers (favorites)")
cust = df.groupby("customer").agg(
    Orders=("order_number","count"),
    Vendors=("brand","nunique"),
    LastOrder=("date","max")
).reset_index()
fav = cust[(cust["Orders"]>=3) | (cust["Vendors"]>=2)]
gb4 = GridOptionsBuilder.from_dataframe(fav)
gb4.configure_default_column(filter=True, sortable=True, resizable=True)
AgGrid(fav, gridOptions=gb4.build(), fit_columns_on_grid_load=True)
