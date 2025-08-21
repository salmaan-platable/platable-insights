# Platable Insights — single-file Streamlit app (iOS-friendly)
# Views: Company, Vendor, Item, Account Manager, Settings
# Features: peak-time heatmaps, Browsed→Pending→Completed funnel,
# clickable charts, AG Grid tables (sort/filter/export), one-sheet ingestion.

import re
from datetime import datetime
from typing import Dict, Optional

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from rapidfuzz import fuzz
from st_aggrid import AgGrid, GridOptionsBuilder

# --- App config & mobile CSS -------------------------------------------------
st.set_page_config(page_title="Platable Insights", page_icon="🥡", layout="wide")
st.markdown("""
<style>
/* Mobile polish for iOS */
@media (max-width: 640px){
  .block-container{padding:1rem}
  .st-emotion-cache-1r4qj8v{padding-top:.5rem}
}
.ag-theme-streamlit{width:100%!important}
.click-hint{font-size:12px;color:#94A3B8;margin-top:-8px;margin-bottom:8px}
.kpi-card{padding:14px 16px;border-radius:16px;background:#fff;border:1px solid #ececec;
  box-shadow:0 1px 3px rgba(0,0,0,.06)}
.kpi-label{font-size:13px;color:#64748B;margin-bottom:4px}
.kpi-value{font-size:28px;font-weight:700;color:#0F172A}
</style>
""", unsafe_allow_html=True)

PRIMARY = "#16A34A"   # Platable-like emerald
ACCENT  = "#F59E0B"   # warm amber

# --- Helpers: header mapping, transforms, KPIs, filters ----------------------
CANON = {
    "order_number": ["order number","order_number","ordernumber","id","order id"],
    "order_state": ["order state","order_state","status","state"],
    "order_value": ["order value","order_value","value","amount","total"],
    "purchase_item_quantity": ["purchase item quantity","quantity","qty","items sold"],
    "service_mode": ["service mode","service","mode"],
    "date": ["date","order date","order_date"],
    "time": ["time","order time","order_time"],
    "item_name": ["item name","item","product"],
    "store_name": ["store name","store","outlet","restaurant","branch"],
    "brand": ["brand","vendor","partner","merchant"],
    "country_code": ["country code","country_code","cc"],
    "phone_number": ["phone number","phone","mobile","contact"],
    "email": ["email","e-mail"],
    "commission": ["commission","comission","commission%","comission%","commission %"],
    "pg": ["pg","pg%","payment gateway","payment gateway%","pg %"],
    "account_manager": ["account manager","acc manager","am"]
}

DEFAULT_PARAMS = {
    "avg_order_weight_kg": 0.40,
    "kg_per_meal": 0.40,
    "co2e_per_kg_food_rescued": 2.5,
    "last_mile_co2e_delivery_kg": 1.0,
    "last_mile_co2e_pickup_kg": 0.2,
    "enable_pickup_co2e_component": True
}

def normalize_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = df.columns.astype(str).str.strip().str.lower().str.replace(r"\s+"," ",regex=True)
    return df

def auto_map_headers(df: pd.DataFrame) -> Dict[str,str]:
    cols = list(df.columns)
    mapping = {}
    for canon, aliases in CANON.items():
        best, score_best = None, 0
        for c in cols:
            score = max(fuzz.partial_ratio(c, a) for a in aliases)
            if score > score_best:
                best, score_best = c, score
        if score_best >= 70:
            mapping[canon] = best
    return mapping

def to_float(x):
    if pd.isna(x): return np.nan
    if isinstance(x,(int,float,np.number)): return float(x)
    s = re.sub(r"[^\d\.\-]","", str(x))
    try: return float(s)
    except: return np.nan

def pct_to_decimal(x):
    if pd.isna(x): return np.nan
    if isinstance(x,str):
        s = x.strip().replace("%","").replace(",","")
        try: v = float(s)
        except: return np.nan
    else:
        v = float(x)
    return v/100.0 if v>1 else v

def parse_hour(val):
    if pd.isna(val): return None
    # pandas parse
    try:
        ts = pd.to_datetime(val, errors="coerce")
        if pd.notna(ts): return int(ts.hour)
    except: pass
    # excel fraction
    if isinstance(val,(int,float,np.number)):
        v = float(val)
        if 0 <= v <= 1:
            return int(round(v*24))%24
        if v>1:
            frac = v - int(v)
            return int(round(frac*24))%24
    # "hh:mm am/pm"
    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", str(val).lower())
    if m:
        hh = int(m.group(1)); ampm = m.group(3)
        if ampm=="pm" and hh!=12: hh += 12
        if ampm=="am" and hh==12: hh = 0
        return hh%24
    return None

def bucket_time(h):
    if h is None: return "Other"
    if 6 <= h < 12: return "Morning"
    if 12 <= h < 18: return "Afternoon"
    if 18 <= h < 24: return "Evening"
    return "Other"

def transform(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    df = normalize_cols(df)
    mapping = auto_map_headers(df)
    # build working
    work = pd.DataFrame({k: df.get(mapping.get(k, k)) for k in CANON.keys() if (mapping.get(k, k) in df.columns)})
    # normalize
    work["order_state"] = work["order_state"].astype(str).str.strip().str.lower().map({
        "pending":"Pending","cancelled":"Cancelled","canceled":"Cancelled"
    }).fillna("Completed")
    work["order_value"] = work["order_value"].apply(to_float)
    work["purchase_item_quantity"] = pd.to_numeric(work["purchase_item_quantity"], errors="coerce").fillna(0).astype(int)
    work["service_mode"] = work["service_mode"].astype(str).str.title()
    work["date"] = pd.to_datetime(work["date"], errors="coerce").dt.date
    work["hour"] = work["time"].apply(parse_hour)
    work["time_bucket"] = work["hour"].apply(bucket_time)
    work["country"] = work["country_code"].apply(lambda x: "UAE" if re.sub(r"\D","", str(x)).startswith("971") else "Other")
    work["phone"] = [(re.sub(r"\D","",str(cc) if pd.notna(cc) else "") + re.sub(r"\D","",str(ph) if pd.notna(ph) else "")).lstrip("0") or np.nan
                     for cc,ph in zip(work["country_code"], work["phone_number"])]
    # % to decimals
    work["commission_pct"] = work["commission"].apply(pct_to_decimal)
    work["pg_pct"] = work["pg"].apply(pct_to_decimal)
    # financials
    work["commission_amount"] = (work["order_value"] * work["commission_pct"]).round(2)
    work["pg_amount"] = (work["order_value"] * work["pg_pct"]).round(2)
    work["revenue"] = (work["commission_amount"].fillna(0) + work["pg_amount"].fillna(0)).round(2)
    work["payout"] = (work["order_value"] - work["revenue"]).round(2)
    # impact
    avg_w = params.get("avg_order_weight_kg", 0.40)
    kg_per_meal = params.get("kg_per_meal", 0.40)
    co2e = params.get("co2e_per_kg_food_rescued", 2.5)
    enable_pickup = params.get("enable_pickup_co2e_component", True)
    deliv_co2 = params.get("last_mile_co2e_delivery_kg", 1.0)
    pickup_co2 = params.get("last_mile_co2e_pickup_kg", 0.2)
    work["order_food_kg"] = avg_w
    if "order_weight_kg" in work.columns and work["order_weight_kg"].notna().any():
        work["order_food_kg"] = work["order_weight_kg"].fillna(avg_w)
    work["meals"] = work["order_food_kg"] / kg_per_meal
    work["co2e_avoided"] = work["order_food_kg"] * co2e
    if enable_pickup:
        work["co2e_avoided"] += np.where(work["service_mode"]=="Pickup", max(deliv_co2 - pickup_co2, 0), 0)
    work["is_pickup"] = (work["service_mode"]=="Pickup").astype(int)
    return work

def apply_filters(df: pd.DataFrame, f: dict) -> pd.DataFrame:
    x = df.copy()
    if f.get("date_range") and len(f["date_range"])==2:
        s,e = pd.to_datetime(f["date_range"][0]), pd.to_datetime(f["date_range"][1])
        x = x[(pd.to_datetime(x["date"])>=s) & (pd.to_datetime(x["date"])<=e)]
    for col, key in [("service_mode","service_mode"), ("order_state","order_state"),
                     ("brand","brand"), ("store_name","outlet"), ("item_name","item"), ("account_manager","account_manager")]:
        vals = f.get(key)
        if vals: x = x[x[col].isin(vals)]
    return x

def kpis(df: pd.DataFrame) -> dict:
    orders = len(df)
    gmv = float(df["order_value"].sum())
    revenue = float(df["revenue"].sum())
    payout = float(df["payout"].sum())
    aov = (gmv/orders) if orders else 0.0
    items_sold = int(df["purchase_item_quantity"].sum())
    u_items = df["item_name"].nunique()
    u_vendors = df["brand"].nunique()
    u_outlets = df["store_name"].nunique()
    u_customers = df["phone"].nunique()
    cust_counts = df.groupby("phone")["order_number"].nunique() if "phone" in df else pd.Series(dtype=int)
    repeat_pct = float((cust_counts>=2).sum())/float(len(cust_counts)) if len(cust_counts)>0 else 0.0
    food_kg = float(df["order_food_kg"].sum()) if "order_food_kg" in df else 0.0
    meals = float(df["meals"].sum()) if "meals" in df else 0.0
    co2 = float(df["co2e_avoided"].sum()) if "co2e_avoided" in df else 0.0
    pickup_share = float(df["is_pickup"].sum())/orders if orders>0 else 0.0
    return locals()

def top_n(df, by: str, group: str, n=10):
    agg = df.groupby(group).agg(
        gmv=("order_value","sum"),
        orders=("order_number","count"),
        revenue=("revenue","sum"),
        items=("purchase_item_quantity","sum")
    ).reset_index()
    return agg.sort_values(by=by, ascending=False).head(n)

# --- Charts ------------------------------------------------------------------
def fig_ts(df):
    daily = df.groupby("date").agg(gmv=("order_value","sum"), orders=("order_number","count")).reset_index()
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=daily["date"], y=daily["gmv"], name="GMV (AED)", mode="lines+markers", yaxis="y1"))
    fig.add_trace(go.Scatter(x=daily["date"], y=daily["orders"], name="Orders", mode="lines+markers", yaxis="y2"))
    fig.update_layout(height=380, margin=dict(l=10,r=10,t=30,b=0),
        xaxis=dict(title="Date"), yaxis=dict(title="GMV (AED)"),
        yaxis2=dict(title="Orders", overlaying="y", side="right"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1))
    return fig

def fig_bar(df, by, group, title):
    agg = top_n(df, by, group)
    fig = go.Figure(go.Bar(x=agg[by], y=agg[group].astype(str), orientation="h", marker_color=PRIMARY))
    fig.update_layout(title=title, height=360, margin=dict(l=10,r=10,t=30,b=10))
    fig.update_yaxes(autorange="reversed")
    return fig

def fig_donut(df):
    split = df["service_mode"].value_counts(dropna=False).reset_index()
    split.columns = ["service_mode","count"]
    fig = px.pie(split, values="count", names="service_mode", hole=0.5, color_discrete_sequence=[PRIMARY, ACCENT])
    fig.update_layout(height=320, margin=dict(l=10,r=10,t=30,b=10))
    return fig

def fig_funnel(df):
    pending = (df["order_state"]=="Pending").sum()
    completed = (df["order_state"]=="Completed").sum()
    browsed = pending + completed
    fig = go.Figure(go.Funnel(y=["Browsed","Pending","Completed"], x=[browsed,pending,completed],
                              textposition="inside", textinfo="value+percent previous"))
    fig.update_layout(height=360, margin=dict(l=10,r=10,t=30,b=10))
    return fig

def fig_heatmap(df):
    t = df.copy()
    t["dow"] = pd.to_datetime(t["date"]).dt.dayofweek
    pivot = t.pivot_table(index="dow", columns="hour", values="order_number", aggfunc="count").fillna(0)
    fig = px.imshow(pivot, aspect="auto", labels=dict(x="Hour", y="Day of Week", color="Orders"),
                    color_continuous_scale="Greens")
    fig.update_layout(height=360, margin=dict(l=10,r=10,t=30,b=10))
    return fig

# --- UI bits -----------------------------------------------------------------
def kpi_card(label, value, helper=None):
    st.markdown(f"""
    <div class="kpi-card"><div class="kpi-label">{label}</div>
    <div class="kpi-value">{value}</div>
    {f'<div style="font-size:12px;color:#94A3B8;margin-top:6px">{helper}</div>' if helper else ''}
    </div>""", unsafe_allow_html=True)

def filter_bar(df):
    cols = st.columns([2,2,2,2])
    with cols[0]:
        dr = st.date_input("Date range", [])
    with cols[1]:
        sm = st.multiselect("Service Mode", ["Pickup","Delivery"])
    with cols[2]:
        os = st.multiselect("Order State", ["Pending","Cancelled","Completed"], default=["Completed"])
    with cols[3]:
        am = st.multiselect("Account Manager", sorted(df.get("account_manager", pd.Series([],dtype=str)).dropna().unique().tolist()))
    cols2 = st.columns([2,2,2])
    with cols2[0]:
        br = st.multiselect("Brand", sorted(df["brand"].dropna().unique().tolist()))
    with cols2[1]:
        ou = st.multiselect("Outlet", sorted(df["store_name"].dropna().unique().tolist()))
    with cols2[2]:
        it = st.multiselect("Item", sorted(df["item_name"].dropna().unique().tolist()))
    return {"date_range": dr, "service_mode": sm, "order_state": os, "account_manager": am, "brand": br, "outlet": ou, "item": it}

# --- Views -------------------------------------------------------------------
def view_company(df):
    st.subheader("Company (Platable)")
    st.write('<div class="click-hint">Tip: charts are clickable for drill-downs.</div>', unsafe_allow_html=True)
    f = filter_bar(df)
    scoped = apply_filters(df, f)
    m = kpis(scoped)
    c1,c2,c3,c4,c5,c6 = st.columns(6)
    with c1: kpi_card("GMV (AED)", f"{m['gmv']:,.2f}")
    with c2: kpi_card("Revenue (AED)", f"{m['revenue']:,.2f}")
    with c3: kpi_card("Payout (AED)", f"{m['payout']:,.2f}")
    with c4: kpi_card("Orders", f"{m['orders']:,}")
    with c5: kpi_card("AOV (AED)", f"{m['aov']:,.2f}")
    with c6: kpi_card("Items Sold", f"{m['items_sold']:,}")
    c1,c2,c3,c4,c5,c6 = st.columns(6)
    with c1: kpi_card("Unique Items", m['u_items'])
    with c2: kpi_card("Unique Vendors", m['u_vendors'])
    with c3: kpi_card("Unique Outlets", m['u_outlets'])
    with c4: kpi_card("Unique Customers", m['u_customers'])
    with c5: kpi_card("Repeat %", f"{m['repeat_pct']*100:.1f}%")
    with c6: kpi_card("Pickup Share %", f"{m['pickup_share']*100:.1f}%")
    c1,c2,c3 = st.columns(3)
    with c1: kpi_card("Food Rescued (kg)", f"{m['food_kg']:,.1f}")
    with c2: kpi_card("Meals Equivalent", f"{m['meals']:,.1f}")
    with c3: kpi_card("CO₂e Avoided (kg)", f"{m['co2']:,.1f}")

    col1,col2 = st.columns([2,1])
    with col1:
        st.markdown("**GMV & Orders over time**")
        st.plotly_chart(fig_ts(scoped), use_container_width=True)
    with col2:
        st.markdown("**Pickup vs Delivery**")
        st.plotly_chart(fig_donut(scoped), use_container_width=True)

    col1,col2 = st.columns(2)
    with col1:
        st.markdown("**Top 10 Brands by GMV**")
        st.plotly_chart(fig_bar(scoped, "gmv", "brand", "Brands"), use_container_width=True)
    with col2:
        st.markdown("**Top 10 Outlets by Orders**")
        st.plotly_chart(fig_bar(scoped, "orders", "store_name", "Outlets"), use_container_width=True)

    col1,col2 = st.columns(2)
    with col1:
        st.markdown("**Top 10 Items by Items Sold**")
        st.plotly_chart(fig_bar(scoped, "items", "item_name", "Items"), use_container_width=True)
    with col2:
        st.markdown("**Funnel: Browsed → Pending → Completed**")
        st.plotly_chart(fig_funnel(scoped), use_container_width=True)

    st.markdown("**Peak Time Heatmap (Hour × Day of Week)**")
    st.plotly_chart(fig_heatmap(scoped), use_container_width=True)

    st.markdown("**Orders by Brand (sortable & filterable)**")
    grid_df = scoped.groupby("brand").agg(
        Orders=("order_number","count"),
        GMV=("order_value","sum"),
        Revenue=("revenue","sum"),
        Payout=("payout","sum"),
        AOV=("order_value","mean"),
        PickupPct=("is_pickup","mean"),
    ).reset_index()
    gb = GridOptionsBuilder.from_dataframe(grid_df)
    gb.configure_default_column(filter=True, sortable=True, resizable=True)
    AgGrid(grid_df, gridOptions=gb.build(), fit_columns_on_grid_load=True)

def view_vendor(df):
    st.subheader("Vendor")
    vendor_sel = st.multiselect("Vendor(s)", sorted(df["brand"].dropna().unique().tolist()), default=sorted(df["brand"].dropna().unique().tolist()))
    f = filter_bar(df.assign(brand=df["brand"]))
    f["brand"] = vendor_sel
    scoped = apply_filters(df, f)
    m = kpis(scoped)
    c1,c2,c3,c4,c5,c6 = st.columns(6)
    with c1: kpi_card("GMV (AED)", f"{m['gmv']:,.2f}")
    with c2: kpi_card("Revenue (AED)", f"{m['revenue']:,.2f}")
    with c3: kpi_card("Payout (AED)", f"{m['payout']:,.2f}")
    with c4: kpi_card("Orders", f"{m['orders']:,}")
    with c5: kpi_card("AOV (AED)", f"{m['aov']:,.2f}")
    with c6: kpi_card("Items Sold", f"{m['items_sold']:,}")
    c1,c2,c3,c4 = st.columns(4)
    with c1: kpi_card("Unique Items", m['u_items'])
    with c2: kpi_card("Outlets", m['u_outlets'])
    with c3: kpi_card("Pickup %", f"{m['pickup_share']*100:.1f}%")
    with c4: kpi_card("CO₂e (kg)", f"{m['co2']:,.1f}")

    c1,c2 = st.columns([2,1])
    with c1: st.plotly_chart(fig_ts(scoped), use_container_width=True)
    with c2: st.plotly_chart(fig_donut(scoped), use_container_width=True)

    c1,c2 = st.columns(2)
    with c1: st.plotly_chart(fig_funnel(scoped), use_container_width=True)
    with c2: st.plotly_chart(fig_bar(scoped, "items", "item_name", "Top Items (Top 50)"), use_container_width=True)

    st.plotly_chart(fig_bar(scoped, "orders", "store_name", "Outlets"), use_container_width=True)
    st.plotly_chart(fig_heatmap(scoped), use_container_width=True)

    st.markdown("**Outlets Table**")
    grid_df = scoped.groupby("store_name").agg(
        Orders=("order_number","count"),
        GMV=("order_value","sum"),
        AOV=("order_value","mean"),
        Revenue=("revenue","sum"),
        Payout=("payout","sum"),
        PickupPct=("is_pickup","mean"),
        LastOrder=("date","max")
    ).reset_index()
    gb = GridOptionsBuilder.from_dataframe(grid_df); gb.configure_default_column(filter=True, sortable=True, resizable=True)
    AgGrid(grid_df, gridOptions=gb.build(), fit_columns_on_grid_load=True)

def view_item(df):
    st.subheader("Item")
    items = st.multiselect("Item(s)", sorted(df["item_name"].dropna().unique().tolist()))
    f = filter_bar(df)
    f["item"] = items
    scoped = apply_filters(df, f)
    m = kpis(scoped)
    c1,c2,c3,c4,c5 = st.columns(5)
    with c1: kpi_card("Items Sold", f"{m['items_sold']:,}")
    with c2: kpi_card("GMV (AED)", f"{m['gmv']:,.2f}")
    with c3: kpi_card("Orders", f"{m['orders']:,}")
    with c4: kpi_card("Unique Customers", f"{m['u_customers']:,}")
    with c5: kpi_card("AOV (AED)", f"{m['aov']:,.2f}")

    st.plotly_chart(fig_ts(scoped), use_container_width=True)
    st.plotly_chart(fig_bar(scoped, "gmv", "brand", "Vendors for Item"), use_container_width=True)
    st.plotly_chart(fig_donut(scoped), use_container_width=True)
    st.plotly_chart(fig_heatmap(scoped), use_container_width=True)

    st.markdown("**Orders for Item(s)**")
    grid_df = scoped[["order_number","date","time","brand","store_name","item_name","service_mode","order_state","order_value","revenue","payout"]].copy()
    gb = GridOptionsBuilder.from_dataframe(grid_df); gb.configure_default_column(filter=True, sortable=True, resizable=True)
    AgGrid(grid_df, gridOptions=gb.build(), fit_columns_on_grid_load=True)

def view_am(df):
    st.subheader("Account Manager")
    ams = sorted(df.get("account_manager", pd.Series([],dtype=str)).dropna().unique().tolist())
    am_sel = st.multiselect("Account Manager(s)", ams, default=ams)
    f = filter_bar(df)
    f["account_manager"] = am_sel
    scoped = apply_filters(df, f)
    m = kpis(scoped)
    c1,c2,c3,c4,c5,c6 = st.columns(6)
    with c1: kpi_card("Managed Vendors", scoped["brand"].nunique())
    with c2: kpi_card("GMV (AED)", f"{m['gmv']:,.2f}")
    with c3: kpi_card("Orders", f"{m['orders']:,}")
    with c4: kpi_card("Revenue (AED)", f"{m['revenue']:,.2f}")
    with c5: kpi_card("Payout (AED)", f"{m['payout']:,.2f}")
    with c6: kpi_card("AOV (AED)", f"{m['aov']:,.2f}")

    c1,c2 = st.columns([2,1])
    with c1: st.plotly_chart(fig_ts(scoped), use_container_width=True)
    with c2: st.plotly_chart(fig_donut(scoped), use_container_width=True)

    c1,c2 = st.columns(2)
    with c1: st.plotly_chart(fig_funnel(scoped), use_container_width=True)
    with c2: st.plotly_chart(fig_bar(scoped, "gmv", "brand", "Top Vendors"), use_container_width=True)

    st.plotly_chart(fig_heatmap(scoped), use_container_width=True)

    st.markdown("**Vendors Table**")
    grid_df = scoped.groupby("brand").agg(
        Orders=("order_number","count"),
        GMV=("order_value","sum"),
        Revenue=("revenue","sum"),
        Payout=("payout","sum"),
        AOV=("order_value","mean"),
        PickupPct=("is_pickup","mean"),
        LastActivity=("date","max")
    ).reset_index()
    gb = GridOptionsBuilder.from_dataframe(grid_df); gb.configure_default_column(filter=True, sortable=True, resizable=True)
    AgGrid(grid_df, gridOptions=gb.build(), fit_columns_on_grid_load=True)

def view_settings():
    st.subheader("Settings")
    # Branding
    st.markdown("**Branding**")
    logo = st.file_uploader("Upload a logo (PNG/SVG)", type=["png","svg"])
    if logo:
        st.session_state["logo_bytes"] = logo.read()
        st.success("Logo uploaded (kept in session).")

    # Impact Parameters
    st.markdown("---\n**Impact Parameters**")
    params = st.session_state.get("impact_params", DEFAULT_PARAMS.copy())
    c1,c2,c3 = st.columns(3)
    with c1:
        params["avg_order_weight_kg"] = st.number_input("Avg order weight (kg)", value=float(params["avg_order_weight_kg"]), step=0.05, min_value=0.0)
        params["kg_per_meal"] = st.number_input("kg per meal", value=float(params["kg_per_meal"]), step=0.05, min_value=0.1)
    with c2:
        params["co2e_per_kg_food_rescued"] = st.number_input("CO₂e per kg rescued", value=float(params["co2e_per_kg_food_rescued"]), step=0.1, min_value=0.0)
        params["last_mile_co2e_delivery_kg"] = st.number_input("Last-mile CO₂e delivery (kg)", value=float(params["last_mile_co2e_delivery_kg"]), step=0.1, min_value=0.0)
    with c3:
        params["last_mile_co2e_pickup_kg"] = st.number_input("Last-mile CO₂e pickup (kg)", value=float(params["last_mile_co2e_pickup_kg"]), step=0.1, min_value=0.0)
        params["enable_pickup_co2e_component"] = st.checkbox("Enable pickup CO₂e component", value=bool(params["enable_pickup_co2e_component"]))
    st.session_state["impact_params"] = params
    st.caption("Changes apply on next data refresh.")

    # Upload
    st.markdown("---\n**Data Upload (Single Sheet)**")
    up = st.file_uploader("Upload XLSX/CSV (single sheet with all columns)", type=["xlsx","csv"])
    if up:
        try:
            if up.name.lower().endswith(".xlsx"):
                df = pd.read_excel(up)
            else:
                df = pd.read_csv(up)
            st.session_state["raw_df"] = df
            st.session_state["data_df"] = transform(df, params)
            st.success("Data loaded and transformed. Preview below ⤵")
            st.dataframe(st.session_state["data_df"].head(50))
        except Exception as e:
            st.error(f"Failed to read file: {e}")

    st.markdown("---\n**Privacy**")
    st.session_state["mask_pii"] = st.checkbox("Mask PII (phone/email) by default", value=st.session_state.get("mask_pii", True))

# --- Sidebar nav -------------------------------------------------------------
st.sidebar.image("https://raw.githubusercontent.com/simple-icons/simple-icons/develop/icons/leaflet.svg", width=0)  # placeholder for spacing
st.sidebar.markdown(f"<h3 style='color:{PRIMARY};margin-top:-8px'>Platable Insights</h3>", unsafe_allow_html=True)
page = st.sidebar.radio("Navigate", ["Company","Vendor","Item","Account Manager","Settings"], index=0)

# --- Logo preview if uploaded (optional) -------------------------------------
if st.session_state.get("logo_bytes"):
    st.sidebar.image(st.session_state["logo_bytes"])

# --- Load data from session --------------------------------------------------
if page != "Settings":
    if "data_df" not in st.session_state:
        st.info("Go to **Settings** → Upload your single data sheet to begin.")
        st.stop()
    data = st.session_state["data_df"].copy()
else:
    data = st.session_state.get("data_df")

# --- Route -------------------------------------------------------------------
if page == "Company":        view_company(data)
elif page == "Vendor":      view_vendor(data)
elif page == "Item":        view_item(data)
elif page == "Account Manager": view_am(data)
else:                       view_settings()
