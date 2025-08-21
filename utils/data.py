\
import pandas as pd
import numpy as np
import re
from rapidfuzz import fuzz

CANON = {
    "order_number": ["order number","order_number","order id","ordernumber","orderno"],
    "order_state": ["order state","order_state","status","state"],
    "order_value": ["order value","gmv","amount","total","value"],
    "purchase_item_quantity": ["purchase item quantity","quantity","qty","items sold"],
    "service_mode": ["service mode","service","mode","fulfillment mode"],
    "date": ["date","order date","order_date"],
    "time": ["time","order time","order_time"],
    "item_name": ["item name","item","product"],
    "store_name": ["store name","store","outlet","restaurant","branch"],
    "brand": ["brand","vendor","partner","merchant"],
    "country_code": ["country code","country_code","cc"],
    "phone_number": ["phone number","phone","mobile","contact"],
    "email": ["email","e-mail"],
    "commission_pct": ["commission%","commission pct","commission rate","commission"],
    "pg_pct": ["pg%","pg pct","payment gateway","pg"],
    "commission_amt": ["commission","commission (aed)","commission aed"],
    "pg_amt": ["pg","pg (aed)","pg aed"],
    "revenue": ["revenue"],
    "payout": ["payout"],
    "account_manager": ["account manager","am","acc manager"]
}

def normalize_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = (
        df.columns.astype(str).str.strip().str.lower().str.replace(r"\s+"," ",regex=True)
    )
    return df

def auto_map_headers(df: pd.DataFrame):
    cols = list(df.columns)
    mapping = {}
    for canon, aliases in CANON.items():
        best, score_best = None, 0
        for c in cols:
            s = max(fuzz.partial_ratio(c, a) for a in aliases)
            if s > score_best:
                best, score_best = c, s
        if score_best >= 70:
            mapping[canon] = best
    return mapping

def parse_hour(val):
    if pd.isna(val): return np.nan
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
    import re
    m = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", str(val).lower())
    if m:
        hh = int(m.group(1)); ampm = m.group(3)
        if ampm=="pm" and hh!=12: hh+=12
        if ampm=="am" and hh==12: hh=0
        return hh%24
    return np.nan

def time_bucket(h):
    if pd.isna(h): return "Other (00–06)"
    if 6 <= h < 12:  return "Morning (06–12)"
    if 12 <= h < 18: return "Afternoon (12–18)"
    if 18 <= h < 24: return "Evening (18–24)"
    return "Other (00–06)"

def transform(df: pd.DataFrame, params: dict) -> pd.DataFrame:
    # Expect your "final" combined sheet; still map headers robustly.
    dfn = normalize_cols(df)
    mp = auto_map_headers(dfn)

    # Build working frame with canonical names
    w = pd.DataFrame({
        "order_number": dfn.get(mp.get("order_number","order number")),
        "order_state": dfn.get(mp.get("order_state","order state")),
        "order_value": dfn.get(mp.get("order_value","order value")),
        "qty": dfn.get(mp.get("purchase_item_quantity","purchase item quantity")),
        "service_mode": dfn.get(mp.get("service_mode","service mode")),
        "date": pd.to_datetime(dfn.get(mp.get("date","date")), errors="coerce").dt.date,
        "time": dfn.get(mp.get("time","time")),
        "item_name": dfn.get(mp.get("item_name","item name")),
        "store_name": dfn.get(mp.get("store_name","store name")),
        "brand": dfn.get(mp.get("brand","brand")),
        "country_code": dfn.get(mp.get("country_code","country code")),
        "phone_number": dfn.get(mp.get("phone_number","phone number")),
        "email": dfn.get(mp.get("email","email")),
        "commission_pct": dfn.get(mp.get("commission_pct","commission%")),
        "pg_pct": dfn.get(mp.get("pg_pct","pg%")),
        "commission": dfn.get(mp.get("commission_amt","commission")),
        "pg": dfn.get(mp.get("pg_amt","pg")),
        "revenue": dfn.get(mp.get("revenue","revenue")),
        "payout": dfn.get(mp.get("payout","payout")),
        "account_manager": dfn.get(mp.get("account_manager","account manager"))
    })

    # Normalize and derive
    w["order_state"] = w["order_state"].astype(str).str.strip().str.title()
    w["service_mode"] = w["service_mode"].astype(str).str.title()
    w["order_value"] = pd.to_numeric(w["order_value"], errors="coerce")
    w["qty"] = pd.to_numeric(w["qty"], errors="coerce").fillna(0).astype(int)
    w["hour"] = w["time"].apply(parse_hour)
    w["time_bucket"] = w["hour"].apply(time_bucket)

    # Customer id
    def comb_phone(cc, pn):
        import re as _re
        digits = (_re.sub(r"\D","", str(cc) if pd.notna(cc) else "") + _re.sub(r"\D","", str(pn) if pd.notna(pn) else "")).lstrip("0")
        return digits if digits else np.nan
    w["customer"] = [comb_phone(cc, pn) if (pd.notna(cc) or pd.notna(pn)) else (em if pd.notna(em) else np.nan)
                     for cc,pn,em in zip(w["country_code"], w["phone_number"], w["email"])]

    # Impact
    avg_w = params.get("avg_order_weight_kg", 0.40)
    kg_per_meal = params.get("kg_per_meal", 0.40)
    co2e = params.get("co2e_per_kg_food_rescued", 2.5)
    enable_pickup = params.get("enable_pickup_co2e_component", True)
    deliv = params.get("last_mile_co2e_delivery_kg", 1.0)
    pickup = params.get("last_mile_co2e_pickup_kg", 0.2)

    w["order_food_kg"] = avg_w
    if "order_weight_kg" in dfn.columns and dfn["order_weight_kg"].notna().any():
        w["order_food_kg"] = pd.to_numeric(dfn["order_weight_kg"], errors="coerce").fillna(avg_w)

    w["meals"] = w["order_food_kg"] / kg_per_meal
    w["co2e_food"] = w["order_food_kg"] * co2e
    w["pickup_co2e_saved"] = 0.0
    if enable_pickup:
        w.loc[w["service_mode"]=="Pickup", "pickup_co2e_saved"] = max(deliv - pickup, 0)
    w["co2e_total"] = w["co2e_food"] + w["pickup_co2e_saved"]

    # pickup flag
    w["is_pickup"] = (w["service_mode"]=="Pickup").astype(int)

    # for KPIs we exclude Cancelled
    w["is_cancelled"] = (w["order_state"]=="Cancelled").astype(int)

    return w

def exclude_cancelled(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["order_state"]!="Cancelled"].copy()

def kpis_company(scoped: pd.DataFrame) -> dict:
    # exclude Cancelled by rule
    x = exclude_cancelled(scoped)
    orders = len(x)
    gmv = float(x["order_value"].sum())
    revenue = float(x.get("revenue", pd.Series(dtype=float)).sum())
    payout = float(x.get("payout", pd.Series(dtype=float)).sum())
    aov = (gmv/orders) if orders else 0.0
    items_sold = int(x["qty"].sum())
    u_items = x["item_name"].nunique()
    u_vendors = x["brand"].nunique()
    u_outlets = x["store_name"].nunique()
    u_customers = x["customer"].nunique()

    cust_counts = x.groupby("customer")["order_number"].nunique(dropna=True)
    repeat_pct = float((cust_counts>=2).sum())/float(len(cust_counts)) if len(cust_counts)>0 else 0.0

    food_kg = float(x["order_food_kg"].sum())
    meals = float(x["meals"].sum())
    co2 = float(x["co2e_total"].sum())
    pickup_share = float(x["is_pickup"].sum())/orders if orders>0 else 0.0
    pickup_co2 = float(x["pickup_co2e_saved"].sum())

    return dict(orders=orders, gmv=gmv, revenue=revenue, payout=payout, aov=aov,
                items_sold=items_sold, u_items=u_items, u_vendors=u_vendors, u_outlets=u_outlets,
                u_customers=u_customers, repeat_pct=repeat_pct, food_kg=food_kg, meals=meals,
                co2=co2, pickup_share=pickup_share, pickup_co2=pickup_co2)

def peak_window_counts(scoped: pd.DataFrame, value="orders"):
    x = exclude_cancelled(scoped)
    if value=="gmv":
        g = x.groupby("time_bucket")["order_value"].sum().reindex(["Morning (06–12)","Afternoon (12–18)","Evening (18–24)","Other (00–06)"]).fillna(0)
    else:
        g = x.groupby("time_bucket")["order_number"].count().reindex(["Morning (06–12)","Afternoon (12–18)","Evening (18–24)","Other (00–06)"]).fillna(0)
    return g.reset_index(names=["time_bucket", value])
