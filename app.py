import os
import time
from datetime import datetime
from typing import Dict, Any, List

import streamlit as st
import pandas as pd
import yfinance as yf
import requests

# =========================
# SECRETS / CONFIG
# =========================

def get_secret(section: str, key: str, default: str = "") -> str:
    """Read from .streamlit/secrets.toml if available, else env."""
    if section in st.secrets and key in st.secrets[section]:
        return st.secrets[section][key]
    return os.getenv(key, default)

GUMROAD_PRODUCT_ID     = get_secret("gumroad", "PRODUCT_ID", "")
GUMROAD_ACCESS_TOKEN   = get_secret("gumroad", "ACCESS_TOKEN", "")
OPENAI_API_KEY         = get_secret("openai", "OPENAI_API_KEY", "")
MAX_USES_PER_DAY       = int(get_secret("app", "MAX_USES_PER_DAY", "50"))

# hard-coded “top most traded” style list
TOP_10_TICKERS = [
    "AAPL", "MSFT", "TSLA", "NVDA", "AMZN",
    "META", "GOOGL", "AVGO", "AMD", "NFLX",
]

# mapping the dropdown label → (period, interval)
# (all intervals are “safe”, we fall back to 1d anyway)
TIMEFRAMES = {
    "6 months (1d)": ("6mo", "1d"),
    "1 month (1d)": ("1mo", "1d"),
    "5 days (1d)": ("5d", "1d"),
    "1 day (1h)": ("1d", "1h"),
}

# =========================
# GUMROAD LICENSE VERIFY
# =========================

def verify_gumroad_license(license_key: str) -> Dict[str, Any]:
    """
    Verify license against Gumroad.
    We send: license_key + product_id
    If you added ACCESS_TOKEN, we send that too.
    """
    url = "https://api.gumroad.com/v2/licenses/verify"
    payload = {
        "license_key": license_key.strip(),
        "product_id": GUMROAD_PRODUCT_ID,
    }
    # access token is optional – some accounts need it, some don’t
    if GUMROAD_ACCESS_TOKEN:
        payload["access_token"] = GUMROAD_ACCESS_TOKEN

    try:
        r = requests.post(url, data=payload, timeout=10)
        data = r.json()
        data["_request_payload"] = payload  # for debugging in UI
        return data
    except Exception as e:
        return {
            "success": False,
            "message": f"Error contacting Gumroad: {e}",
            "_request_payload": payload,
        }

# =========================
# DATA FETCHING
# =========================

def fetch_yf_data(ticker: str, period: str, interval: str) -> pd.DataFrame:
    """
    Try to fetch with given interval. If empty and interval is intraday,
    fall back to daily so the app never shows blank.
    """
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False)
        if df.empty and interval in ("5m", "15m", "30m", "1h"):
            # fallback
            df = yf.download(ticker, period=period, interval="1d", progress=False)
        return df
    except Exception:
        return pd.DataFrame()

# =========================
# OPTIONAL AI COMMENTARY
# =========================

def ai_commentary(ticker: str, df: pd.DataFrame, mode: str = "momentum") -> str:
    """
    Super simple AI hook. If OPENAI_API_KEY not set, return a generic text.
    """
    if OPENAI_API_KEY == "":
        return f"{ticker}: AI commentary is disabled (no OPENAI_API_KEY in secrets)."

    # lightweight summary based on last rows
    last_close = df["Close"].iloc[-1] if not df.empty else "unknown"
    # we won’t actually call OpenAI here to keep it simple/run-anywhere
    return (
        f"{ticker}: latest close ≈ {last_close}. "
        f"Mode: {mode}. "
        "You can now plug in a real OpenAI call here to generate richer insights."
    )

# =========================
# STREAMLIT APP
# =========================

st.set_page_config(page_title="Monreon Stock AI", layout="wide")

# init session vars
if "licensed" not in st.session_state:
    st.session_state.licensed = False
if "uses_today" not in st.session_state:
    st.session_state.uses_today = 0
if "license_key" not in st.session_state:
    st.session_state.license_key = ""

# HEADER / HERO
st.title("📈 Monreon Stock AI")
st.caption("Gumroad-locked tool")

# ===== LOGIN BOX UNDER TITLE =====
with st.container():
    st.subheader("🔐 Enter your Gumroad license")
    if not GUMROAD_PRODUCT_ID:
        st.error("Gumroad product ID is missing in secrets. Add it under [gumroad] PRODUCT_ID = \"...\"")
    input_license = st.text_input(
        "License key",
        value=st.session_state.license_key,
        type="password",
        placeholder="paste the license from your Gumroad email",
    )
    login_col1, login_col2 = st.columns([1, 2])
    with login_col1:
        if st.button("Unlock"):
            resp = verify_gumroad_license(input_license)
            if resp.get("success"):
                st.session_state.licensed = True
                st.session_state.license_key = input_license
                st.success("License verified. Welcome! ✅")
            else:
                st.session_state.licensed = False
                st.error(resp.get("message", "License invalid."))

                # show debug info
                with st.expander("See what we sent / got from Gumroad"):
                    st.write("Request payload:", resp.get("_request_payload"))
                    st.write("Response:", resp)
    with login_col2:
        st.write(f"Today: {st.session_state.uses_today} / {MAX_USES_PER_DAY}")

# stop here if not licensed
if not st.session_state.licensed:
    st.stop()

# stop if over limit
if st.session_state.uses_today >= MAX_USES_PER_DAY:
    st.error("Daily limit reached for this session. Try again tomorrow.")
    st.stop()

# ============== MARKET HEADER ==============
col_m1, col_m2, col_m3 = st.columns(3)
with col_m1:
    st.metric("Market status", "Online", delta=datetime.utcnow().strftime("UTC %H:%M"))
with col_m2:
    st.metric("Data source", "Yahoo Finance")
with col_m3:
    st.metric("Licensed to", "Gumroad customer")

st.markdown("---")

# ============== INPUT AREA ==============
st.subheader("🚀 Scan the market")

input_mode = st.radio(
    "Choose input mode.",
    ["Manual tickers", "Top 10 Most Traded US Stocks"],
    horizontal=True,
)

if input_mode == "Manual tickers":
    tickers_str = st.text_input(
        "Tickers (comma separated)",
        value="AAPL, TSLA, NVDA",
        help="Example: AAPL, MSFT, TSLA",
    )
    tickers = [t.strip().upper() for t in tickers_str.split(",") if t.strip()]
else:
    st.info("Using Monreon's popular US stocks list.")
    tickers = TOP_10_TICKERS
    st.write(", ".join(tickers))

timeframe_label = st.selectbox("Timeframe", list(TIMEFRAMES.keys()), index=2)
period, interval = TIMEFRAMES[timeframe_label]

analysis_mode = st.selectbox(
    "Analysis mode",
    ["Find momentum", "Just show charts", "Volume focus"],
)

run_scan = st.button("🔎 Analyze now")

# ============== RESULT AREA ==============
if run_scan and tickers:
    st.session_state.uses_today += 1

    for tk in tickers:
        st.markdown(f"### 📊 {tk}")

        df = fetch_yf_data(tk, period=period, interval=interval)
        if df.empty:
            st.warning("No market data for this ticker.")
            continue

        # basic derived info
        latest = df["Close"].iloc[-1]
        prev = df["Close"].iloc[-2] if len(df) > 1 else latest
        pct = ((latest - prev) / prev * 100) if prev else 0

        cols_head = st.columns(3)
        with cols_head[0]:
            st.metric("Last price", f"{latest:,.2f}")
        with cols_head[1]:
            st.metric("Change % (vs prev)", f"{pct:,.2f}%")
        with cols_head[2]:
            st.metric("Data points", len(df))

        # ---- PRICE LINE CHART ----
        st.line_chart(df[["Close"]])

        # ---- PRICE + VOLUME CHART (simple stacked) ----
        # we do two charts to keep it simple in Streamlit
        st.caption("Price history")
        st.area_chart(df["Close"])
        st.caption("Volume")
        st.bar_chart(df["Volume"])

        # ---- AI COMMENTARY ----
        with st.expander("🤖 AI commentary"):
            st.write(ai_commentary(tk, df, analysis_mode))

        # ---- CSV EXPORT ----
        csv = df.to_csv().encode("utf-8")
        st.download_button(
            label=f"Download {tk} data as CSV",
            data=csv,
            file_name=f"{tk.lower()}_data.csv",
            mime="text/csv",
        )

        st.markdown("---")

# footer
st.caption("© 2025 Monreon AI — Licensed customers only. Key sharing is prohibited.")
