\
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd

PRIMARY = "#F64B6F"
ACCENT  = "#94A3B8"

def bar_peak(df_counts: pd.DataFrame, value_col: str):
    fig = px.bar(df_counts, x="time_bucket", y=value_col, text=value_col, color_discrete_sequence=[PRIMARY])
    fig.update_traces(textposition="outside")
    fig.update_layout(height=360, margin=dict(l=10,r=10,t=10,b=10), xaxis_title="", yaxis_title=value_col.title())
    return fig

def donut_service_mode(df_scoped: pd.DataFrame):
    split = df_scoped[df_scoped["order_state"]!="Cancelled"]["service_mode"].value_counts().reset_index()
    split.columns = ["service_mode","orders"]
    if split.empty:
        split = pd.DataFrame({"service_mode":[], "orders":[]})
    fig = px.pie(split, values="orders", names="service_mode", hole=0.5, color_discrete_sequence=[PRIMARY,"#FFD166"])
    fig.update_layout(height=320, margin=dict(l=10,r=10,t=10,b=10))
    return fig

def bar_top(df_scoped: pd.DataFrame, group: str, metric: str, n: int, asc=False):
    x = df_scoped[df_scoped["order_state"]!="Cancelled"].copy()
    agg = x.groupby(group).agg(
        Orders=("order_number","count"),
        GMV=("order_value","sum"),
        Items=("qty","sum"),
        Revenue=("revenue","sum")
    ).reset_index()
    agg = agg.sort_values(metric, ascending=asc).head(n)
    if metric not in agg.columns:
        metric = "GMV"
    fig = px.bar(agg, x=metric, y=group, orientation="h", color_discrete_sequence=[PRIMARY])
    fig.update_layout(height=380, margin=dict(l=10,r=10,t=10,b=10))
    fig.update_yaxes(autorange="reversed")
    return fig, agg
