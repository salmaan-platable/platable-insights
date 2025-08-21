# Platable – Simple Dashboard (iOS friendly)
# Layout: KPI strip -> Impact strip -> 3 charts row (Pickup vs Delivery, Funnel, Peak window)
# Click any chart element to show a drill-down orders table with sort/filter/export.

import re
from typing import Dict

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from rapidfuzz import fuzz
from st_aggrid import AgGrid, GridOptionsBuilder
from streamlit_plotly_events import plotly_events

# ---------- Basic styling / theme ----------
st.set_page_config(page_title="Platable Insights", page_icon="🥡", layout="wide")
PRIMARY = "#16A34A"   # Platable-ish emerald
ACCENT  = "#F59E0B"   # warm amber

st.markdown("""
<style>
@media (max-width: 640px){
  .block-container{padding:1rem}
  .st-emotion-cache-1r4qj8v{padding-top:.5rem}
}
.kpi{padding:14px 16px;border-radius:16px;background:#fff;border:1px solid #ececec;
    box-shadow:0 1px 3px rgba(0,0,0,.06)}
.kpi .label{font-size:13px;color:#64748B;margin-bottom:4px}
.kpi .val{font-size:28px;font-weight:700;color:#0F172A}
.section-title{font-weight:800;margin:4px 0 8px 0}
.click-hint{font-size:12px;color:#94A3B8;margin:-6px 0 10px 2px}
</style>
""", unsafe_allow_html=True)

# ---------- Header mapping & transforms ----------
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

PARAMS_DEFAULT = dict(
    avg_order_weight_kg=0.40,
    kg_per_meal=0.40,
    co2e_per_kg_food_rescued=2.5,
    last_mile_co2e_delivery_kg=1.0,
    last_mile_co2e_pickup_kg=0.2,
    enable_pickup_co2e_component=True,
    est_value_multiplier=2.0  # for "Est. actual value" tile (editable in Settings)
)

def normalize_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = df.columns.astype(str).str.strip().str.lower().str.replace(r"\s+"," ",regex=True)
    return df

def auto_map_headers(df: pd.DataFrame) -> Dict[str,str]:
    cols = list(df.columns)
    mapping = {}
    for canon, aliases in CANON.items():
        best, best_score = None, 0
        for c in cols:
            s = max(fuzz.partial_ratio(c, a) for a in aliases)
            if s > best_score:
                best, best_score = c, s
        if best_score >= 70:
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
    try:
        ts = pd.to_datetime(val, errors="coerce")
        if pd.notna(ts): return int(ts.hour)
    except: pass
    if isinstance(val,(int,float,np.number)):
        v = float(val)
        if 0 <= v <= 1:  # Excel time fraction
            return int(round(v*24))%24
        if v>1:  # Excel serial
            frac = v - int(v)
            return int(round(frac*24))%24
    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", str(val).lower())
    if m:
        hh = int(m.group(1)); ampm = m.group(3)
        if ampm=="pm" and hh!=12: hh += 12
        if ampm=="am" and hh==12: hh = 0
        return hh%24
    return None

def time_bucket(h):
    if h is None: return "Outside (0–6)"
    if 6 <= h < 12:  return "Morning (06:00–12:00)"
    if 12 <= h < 18: return "Afternoon (12:00–18:00)"
    if 18 <= h < 24: return "Evening (18:00–24:00)"
    return "Outside (0–6)"

def transform(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    df = normalize_cols(df)
    mp = auto_map_headers(df)
    w = pd.DataFrame({k: df.get(mp.get(k, k)) for k in CANON.keys() if (mp.get(k, k) in df.columns)})

    w["order_state"] = w["order_state"].astype(str).str.strip().str.lower().map({
        "pending":"Pending","cancelled":"Cancelled","canceled":"Cancelled"
    }).fillna("Completed")
    w["order_value"] = w["order_value"].apply(to_float)
    w["purchase_item_quantity"] = pd.to_numeric(w["purchase_item_quantity"], errors="coerce").fillna(0).astype(int)
    w["service_mode"] = w["service_mode"].astype(str).str.title()
    w["date"] = pd.to_datetime(w["date"], errors="coerce").dt.date
    w["hour"] = w["time"].apply(parse_hour)
    w["time_bucket"] = w["hour"].apply(time_bucket)
    w["phone"] = [(re.sub(r"\\D","",str(cc) if pd.notna(cc) else "") + re.sub(r"\\D","",str(ph) if pd.notna(ph) else "")).lstrip("0") or np.nan
                  for cc,ph in zip(w["country_code"], w["phone_number"])]

    w["commission_pct"] = w["commission"].apply(pct_to_decimal)
    w["pg_pct"] = w["pg"].apply(pct_to_decimal)
    w["commission_amount"] = (w["order_value"] * w["commission_pct"]).round(2)
    w["pg_amount"] = (w["order_value"] * w["pg_pct"]).round(2)
    w["revenue"] = (w["commission_amount"].fillna(0) + w["pg_amount"].fillna(0)).round(2)
    w["payout"] = (w["order_value"] - w["revenue"]).round(2)

    # Impact
    avg_w = params["avg_order_weight_kg"]
    kg_per_meal = params["kg_per_meal"]
    co2e = params["co2e_per_kg_food_rescued"]
    enable_pickup = params["enable_pickup_co2e_component"]
    deliv_co2 = params["last_mile_co2e_delivery_kg"]
    pickup_co2 = params["last_mile_co2e_pickup_kg"]

    w["order_food_kg"] = avg_w
    if "order_weight_kg" in w and w["order_weight_kg"].notna().any():
        w["order_food_kg"] = w["order_weight_kg"].fillna(avg_w)
    w["meals"] = w["order_food_kg"] / kg_per_meal

    # split CO2 saved so we can show tiles like your screenshot
    w["co2_saved_food"] = w["order_food_kg"] * co2e
    w["co2_saved_last_mile"] = 0.0
    if enable_pickup:
        w.loc[w["service_mode"]=="Pickup", "co2_saved_last_mile"] = max(deliv_co2 - pickup_co2, 0)

    w["is_pickup"] = (w["service_mode"]=="Pickup").astype(int)
    return w

def kpi(df):
    orders = len(df)
    gmv = float(df["order_value"].sum())
    rev = float(df["revenue"].sum())
    payout = float(df["payout"].sum())
    aov = (gmv / orders) if orders else 0.0
    brands = df["brand"].nunique()
    outlets = df["store_name"].nunique()
    customers = df["phone"].nunique()
    return dict(orders=orders, gmv=gmv, revenue=rev, payout=payout, aov=aov,
                brands=brands, outlets=outlets, customers=customers)

# ---------- Sidebar: Settings + Data Upload ----------
st.sidebar.markdown(f"<h3 style='color:{PRIMARY}'>Platable</h3>", unsafe_allow_html=True)
st.sidebar.caption("Simple Dashboard")

# Impact parameters & est. value multiplier
if "params" not in st.session_state:
    st.session_state["params"] = PARAMS_DEFAULT.copy()
P = st.session_state["params"]

with st.sidebar.expander("Impact & Value parameters"):
    P["avg_order_weight_kg"] = st.number_input("Avg order weight (kg)", value=float(P["avg_order_weight_kg"]), step=0.05, min_value=0.0)
    P["kg_per_meal"] = st.number_input("kg per meal", value=float(P["kg_per_meal"]), step=0.05, min_value=0.1)
    P["co2e_per_kg_food_rescued"] = st.number_input("CO₂e per kg rescued", value=float(P["co2e_per_kg_food_rescued"]), step=0.1, min_value=0.0)
    P["last_mile_co2e_delivery_kg"] = st.number_input("Last-mile CO₂e (delivery)", value=float(P["last_mile_co2e_delivery_kg"]), step=0.1, min_value=0.0)
    P["last_mile_co2e_pickup_kg"] = st.number_input("Last-mile CO₂e (pickup)", value=float(P["last_mile_co2e_pickup_kg"]), step=0.1, min_value=0.0)
    P["enable_pickup_co2e_component"] = st.checkbox("Add last-mile pickup savings", value=bool(P["enable_pickup_co2e_component"]))
    P["est_value_multiplier"] = st.number_input("Est. actual value multiplier × GMV", value=float(P["est_value_multiplier"]), step=0.1, min_value=0.0)

st.sidebar.markdown("---")
up = st.sidebar.file_uploader("Upload single sheet (XLSX/CSV)", type=["xlsx","csv","xls"])
if up is not None:
    try:
        ext = up.name.lower().split(".")[-1]
        if ext == "xlsx":
            import openpyxl  # ensure engine is present
            raw = pd.read_excel(up, engine="openpyxl")
        elif ext == "xls":
            import xlrd
            raw = pd.read_excel(up, engine="xlrd")
        else:
            raw = pd.read_csv(up)
        st.session_state["data"] = transform(raw, P)
        st.sidebar.success("Data loaded")
    except Exception as e:
        st.sidebar.error(f"Failed to read file: {e}")

st.title("Company overview")
st.write('<div class="click-hint">Tip: tap bars/stages to open the drill table.</div>', unsafe_allow_html=True)

if "data" not in st.session_state:
    st.info("Upload your XLSX/CSV in the left sidebar to begin.")
    st.stop()

df = st.session_state["data"]

# ---------- KPI strip ----------
M = kpi(df)
cols = st.columns(7)
tiles = [
    ("GMV", f"AED {M['gmv']:,.2f}"),
    ("Payout", f"AED {M['payout']:,.2f}"),
    ("Revenue", f"AED {M['revenue']:,.2f}"),
    ("Brands", f"{M['brands']}"),
    ("Outlets", f"{M['outlets']}"),
    ("Customers", f"{M['customers']}"),
    ("AOV", f"AED {M['aov']:,.2f}"),
]
for (label, val), c in zip(tiles, cols):
    with c:
        st.markdown(f"<div class='kpi'><div class='label'>{label}</div><div class='val'>{val}</div></div>", unsafe_allow_html=True)

# ---------- Impact strip ----------
# Build tiles similar to your screenshot
co2_food = df["co2_saved_food"].sum()
food_kg = df["order_food_kg"].sum()
est_value = M["gmv"] * P["est_value_multiplier"]
cust_savings = max(est_value - M["gmv"], 0)
co2_last_mile = df["co2_saved_last_mile"].sum()
pickups = int(df["is_pickup"].sum())

st.markdown("<div class='section-title'>🌿 Impact</div>", unsafe_allow_html=True)
cols = st.columns(6)
impact_tiles = [
    ("CO₂ saved [food]", f"{co2_food:,.1f} kg"),
    ("Food saved", f"{food_kg:,.1f} kg"),
    ("Est. actual value", f"AED {est_value:,.2f}"),
    ("Customer savings", f"AED {cust_savings:,.2f}"),
    ("CO₂ saved — last mile", f"{co2_last_mile:,.2f} kg"),
    ("Pickups", f"{pickups:,}")
]
for (label, val), c in zip(impact_tiles, cols):
    with c:
        st.markdown(f"<div class='kpi'><div class='label'>{label}</div><div class='val'>{val}</div></div>", unsafe_allow_html=True)

# ---------- Three charts row ----------
c1, c2, c3 = st.columns([1.1, 1.2, 1.1])

# 1) Pickup vs Delivery (bar)
with c1:
    st.markdown("### 🚚 Pickup vs Delivery")
    split = df["service_mode"].value_counts().reset_index()
    split.columns = ["service_mode","orders"]
    fig_pd = px.bar(split, x="service_mode", y="orders", text="orders",
                    color="service_mode", color_discrete_sequence=[PRIMARY, ACCENT])
    fig_pd.update_traces(textposition="outside")
    fig_pd.update_layout(height=380, margin=dict(l=10,r=10,t=10,b=10))
    clicked_pd = plotly_events(fig_pd, click_event=True, hover_event=False, select_event=False, override_height=380, override_width="100%")

# 2) Funnel (Browsed -> Pending -> Ordered)
with c2:
    st.markdown("### 🧭 Funnel (Browsed→Pending→Ordered)")
    pending = (df["order_state"]=="Pending").sum()
    ordered = (df["order_state"]=="Completed").sum()  # Ordered==Completed per your rule
    browsed = pending + ordered
    stages = ["Browsed","Pending","Ordered"]
    values = [browsed, pending, ordered]
    fig_f = go.Figure(go.Funnel(y=stages, x=values, textposition="inside", textinfo="value+percent previous"))
    fig_f.update_layout(height=380, margin=dict(l=10,r=10,t=10,b=10))
    clicked_f = plotly_events(fig_f, click_event=True, hover_event=False, select_event=False, override_height=380, override_width="100%")

# 3) Peak window (time_bucket)
with c3:
    st.markdown("### ⏰ Peak window")
    tb = df.groupby("time_bucket").agg(orders=("order_number","count")).reset_index()
    # fixed order for readability
    bucket_order = ["Afternoon (12:00–18:00)","Evening (18:00–24:00)","Morning (06:00–12:00)","Outside (0–6)"]
    tb["time_bucket"] = pd.Categorical(tb["time_bucket"], categories=bucket_order, ordered=True)
    tb = tb.sort_values("time_bucket")
    fig_peak = px.bar(tb, x="time_bucket", y="orders", text="orders", color_discrete_sequence=[PRIMARY])
    fig_peak.update_traces(textposition="outside")
    fig_peak.update_layout(height=380, margin=dict(l=10,r=10,t=10,b=10), xaxis_title="", yaxis_title="orders")
    clicked_peak = plotly_events(fig_peak, click_event=True, hover_event=False, select_event=False, override_height=380, override_width="100%")

# ---------- Drill table logic ----------
mask = pd.Series(True, index=df.index)

# From Pickup vs Delivery click
if clicked_pd:
    mode = clicked_pd[0]["x"]
    mask &= (df["service_mode"] == mode)

# From Funnel click
if clicked_f:
    stage = clicked_f[0]["y"]
    if stage == "Pending":
        mask &= (df["order_state"]=="Pending")
    elif stage == "Ordered":
        mask &= (df["order_state"]=="Completed")
    elif stage == "Browsed":
        mask &= df["order_state"].isin(["Pending","Completed"])

# From Peak window click
if clicked_peak:
    bucket = clicked_peak[0]["x"]
    mask &= (df["time_bucket"] == bucket)

drilled = df[mask].copy()

st.markdown("### 🔎 Details")
st.caption("Sortable, filterable table. Use the column menu to filter, and the download icon to export CSV.")
show_cols = ["order_number","date","time","brand","store_name","item_name","service_mode","order_state",
             "order_value","commission_amount","pg_amount","revenue","payout"]
if not set(show_cols).issubset(drilled.columns):
    show_cols = [c for c in show_cols if c in drilled.columns]
grid_df = drilled[show_cols].sort_values("date", ascending=False)

gb = GridOptionsBuilder.from_dataframe(grid_df)
gb.configure_default_column(filter=True, sortable=True, resizable=True)
gb.configure_grid_options(domLayout="normal")
AgGrid(grid_df, gridOptions=gb.build(), fit_columns_on_grid_load=True)
