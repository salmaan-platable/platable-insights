\
import streamlit as st

PRIMARY = "#F64B6F"

def inject_fonts_and_css():
    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&family=Manrope:wght@500;700&display=swap');
    html, body, [class*="css"]  { font-family: Inter, Manrope, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, "Noto Sans", "Apple Color Emoji", "Segoe UI Emoji"; }
    .kpi-card{padding:14px 16px;border-radius:16px;background:#fff;border:1px solid #ECECEC;box-shadow:0 1px 3px rgba(0,0,0,.06);}
    .kpi-label{font-size:13px;color:#64748B;margin-bottom:4px}
    .kpi-value{font-size:28px;font-weight:800;color:#0F172A}
    .section-title{font-weight:800;margin:6px 0 10px 0}
    .click-hint{font-size:12px;color:#94A3B8;margin:-6px 0 10px 2px}
    @media (max-width: 640px){
      .block-container{padding:1rem}
    }
    </style>
    """, unsafe_allow_html=True)

def kpi(label, value, helper=None):
    st.markdown(f"""
    <div class="kpi-card">
      <div class="kpi-label">{label}</div>
      <div class="kpi-value">{value}</div>
      {f'<div style="font-size:12px;color:#94A3B8;margin-top:6px">{helper}</div>' if helper else ''}
    </div>
    """, unsafe_allow_html=True)
