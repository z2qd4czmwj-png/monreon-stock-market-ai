import streamlit as st
import requests
import pandas as pd
import yfinance as yf
from datetime import date

# --- CONFIG ---
GUMROAD_PRODUCT_PERMALINK = "aikbve"  # your Gumroad product permalink
OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY", "")
MAX_USES_PER_DAY = int(st.secrets.get("MAX_USES_PER_DAY", 50))

# --- VERIFY LICENSE (working simple version) ---
def verify_gumroad_license(license_key):
    url = "https://api.gumroad.com/v2/licenses/verify"
    payload = {
        "product_permalink": GUMROAD_PRODUCT_PERMALINK,
        "license_key": license_key.strip(),
    }
    try:
        res = requests.post(url, data=payload, timeout=10)
        return res.json()
    except Exception as e:
        return {"success": False, "message": str(e)}

# --- PAGE SETUP ---
st.set_page_config(page_title="Monreon Stock AI", layout="wide")
st.title("📈 Monreon Stock AI — Real-Time Market Research Tool")
st.caption("AI-powered stock research • Protected with Gumroad license access")

# --- LOGIN BOX ---
if "auth" not in st.session_state:
    st.session_state["auth"] = False

if not st.session_state["auth"]:
    st.subheader("🔐 Enter your Gumroad license key")
    key = st.text_input("License key", type="password")
    if st.button("Unlock access"):
        data = verify_gumroad_license(key)
        if data.get("success"):
            st.session_state["auth"] = True
            st.session_state["license"] = key
            st.success("✅ License verified successfully!")
            st.rerun()
        else:
            st.error(data.get("message", "Invalid license."))
    st.stop()

# --- STOCK DATA ---
st.header("📊 Market Analysis")

tickers = st.text_input("Enter stock tickers (comma separated)", "AAPL, TSLA, NVDA")
period = st.selectbox("Select time period", ["1mo", "3mo", "6mo", "1y"], index=2)

if st.button("Analyze"):
    ticker_list = [t.strip().upper() for t in tickers.split(",")]
    for ticker in ticker_list:
        st.subheader(f"📈 {ticker}")
        df = yf.download(ticker, period=period, interval="1d")
        if df.empty:
            st.warning("No data found.")
            continue

        st.line_chart(df["Close"])
        st.bar_chart(df["Volume"].tail(30))

        latest = df["Close"].iloc[-1]
        prev = df["Close"].iloc[-2] if len(df) > 1 else latest
        pct = (latest - prev) / prev * 100 if prev != 0 else 0
        st.metric(label=f"{ticker} Last Price", value=f"${latest:,.2f}", delta=f"{pct:+.2f}%")

st.caption("© 2025 Monreon AI — Gumroad license required for access.")
