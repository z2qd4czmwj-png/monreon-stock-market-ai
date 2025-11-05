import os
import json
import datetime
from typing import List, Dict, Any, Optional

import streamlit as st
import pandas as pd
import yfinance as yf
import requests

# =========================
# CONFIG / SECRETS HELPERS
# =========================

def get_secret(section: str, key: str, default: str = "") -> str:
    """Read from Streamlit secrets first, then env vars."""
    if section in st.secrets and key in st.secrets[section]:
        return st.secrets[section][key]
    return os.getenv(key, default)


# ---- read secrets ----
GUMROAD_PRODUCT_ID = get_secret("gumroad", "PRODUCT_ID", "")   # <- the real product id from JSON
GUMROAD_ACCESS_TOKEN = get_secret("gumroad", "ACCESS_TOKEN", "")  # optional
OPENAI_API_KEY = get_secret("openai", "OPENAI_API_KEY", "")       # optional
MAX_USES_PER_DAY = int(get_secret("app", "MAX_USES_PER_DAY", "50"))

# =========================
# GUMROAD LICENSE VERIFY
# =========================

def verify_gumroad_license(license_key: str) -> Dict[str, Any]:
    """
    Call Gumroad license verify endpoint.
    We always send the product_id (NOT permalink).
    If ACCESS_TOKEN is present, we send it too.
    """
    url = "https://api.gumroad.com/v2/licenses/verify"
    payload = {
        "license_key": license_key.strip(),
        "product_id": GUMROAD_PRODUCT_ID,
    }
    if GUMROAD_ACCESS_TOKEN:
        payload["access_token"] = GUMROAD_ACCESS_TOKEN

    try:
        resp = requests.post(url, data=payload, timeout=10)
        data = resp.json()
        return data
    except Exception as e:
        return {
            "success": False,
            "message": f"Request to Gumroad failed: {e}",
        }


def check_daily_quota() -> bool:
    """True if user still has uses left today."""
    today = datetime.date.today().isoformat()
    if "usage" not in st.session_state:
        st.session_state["usage"] = {}
    usage = st.session_state["usage"]
    used_today = usage.get(today, 0)
    return used_today < MAX_USES_PER_DAY


def record_usage():
    today = datetime.date.today().isoformat()
    if "usage" not in st.session_state:
        st.session_state["usage"] = {}
    st.session_state["usage"][today] = st.session_state["usage"].get(today, 0) + 1


# =========================
# DATA FETCHING
# =========================

def fetch_price_data(
    ticker: str,
    period: str = "5d",
    interval: str = "30m",
) -> Optional[pd.DataFrame]:
    """
    Fetch OHLCV with yfinance.
    Returns None if no data.
    """
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False)
        if df is None or df.empty:
            return None
        df = df.reset_index()
        return df
    except Exception:
        return None


# simple timeframe map from the selectbox label
TIMEFRAME_MAP = {
    "5 days (1d)": ("5d", "1d"),
    "5 days (30m)": ("5d", "30m"),
    "1 month (1d)": ("1mo", "1d"),
    "3 months (1d)": ("3mo", "1d"),
    "1 year (1d)": ("1y", "1d"),
}

# static “most traded” for now
TOP_10_MOST_TRADED_US = [
    "AAPL", "TSLA", "NVDA", "MSFT", "AMZN",
    "META", "GOOGL", "AVGO", "AMD", "NFLX"
]

# =========================
# AI COMMENT (optional)
# =========================

def ai_comment_on_ticker(ticker: str, momentum: float, latest_price: float) -> str:
    """
    Very lightweight stub. If OPENAI key exists, we give a nicer sentence.
    We won't actually call OpenAI here to keep it simple.
    """
    if not OPENAI_API_KEY:
        # fallback text
        if momentum > 0:
            return f"{ticker} shows positive short-term price change. Watch for continuation."
        elif momentum < 0:
            return f"{ticker} is pulling back today. Could be rotation or profit-taking."
        else:
            return f"{ticker} is flat today."
    else:
        # pretend AI answer (you can plug real call here)
        direction = "bullish" if momentum > 0 else "bearish" if momentum < 0 else "neutral"
        return (
            f"AI view ({direction}): {ticker} moved {momentum:.2f}% over the last candle. "
            f"Current price around ${latest_price:.2f}. Consider volume and broader market before acting."
        )


# =========================
# STREAMLIT APP
# =========================

st.set_page_config(page_title="Monreon Stock AI", layout="wide")

st.title("📈 Monreon Stock AI — Market Scanner")
st.caption("Gumroad-locked tool · licensed customers only")

# ---- License box at the TOP (not in sidebar) ----
with st.container(border=True):
    st.subheader("🔐 Enter your Gumroad license")
    lic = st.text_input("License key", type="password")

    if st.button("Unlock", type="primary"):
        if not GUMROAD_PRODUCT_ID:
            st.error("Gumroad product_id is missing in Streamlit secrets. Add it under [gumroad].")
        elif not lic:
            st.error("Please enter a license key.")
        else:
            data = verify_gumroad_license(lic)
            if data.get("success"):
                st.session_state["licensed"] = True
                st.session_state["license_key"] = lic
                st.success("✅ License verified. Welcome!")
            else:
                st.session_state["licensed"] = False
                st.error(f"❌ {data.get('message','License could not be verified.')}")

# show today's usage
today = datetime.date.today().isoformat()
used = st.session_state.get("usage", {}).get(today, 0)
st.caption(f"Today: {used} / {MAX_USES_PER_DAY}")

# ---- stop here if not licensed ----
if not st.session_state.get("licensed", False):
    st.info("Enter a valid Gumroad license above to use the tool.")
    st.stop()

# ---- if licensed but exceeded daily cap ----
if not check_daily_quota():
    st.error("You have reached today's analysis limit. Please come back tomorrow.")
    st.stop()

# =========================
# MARKET HEADER
# =========================
with st.container(border=True):
    st.subheader("📰 Market quick-look")
    st.write(
        "This is a simple header. We can later pull real indexes (SPY, QQQ, DIA) "
        "and show % change here."
    )

st.divider()

# =========================
# MAIN ANALYSIS FORM
# =========================
col1, col2, col3 = st.columns(3)
with col1:
    input_mode = st.radio(
        "Choose input mode:",
        ["Manual tickers", "Top 10 Most Traded US Stocks"],
        horizontal=False,
    )
with col2:
    timeframe_label = st.selectbox(
        "Timeframe",
        list(TIMEFRAME_MAP.keys()),
        index=1,  # default "5 days (30m)"
    )
with col3:
    analysis_mode = st.selectbox(
        "Analysis mode",
        ["Find momentum", "Show latest", "Volume focus"],
    )

if input_mode == "Manual tickers":
    raw_tickers = st.text_input("Tickers (comma separated)", value="AAPL, TSLA, NVDA")
    tickers = [t.strip().upper() for t in raw_tickers.split(",") if t.strip()]
else:
    st.info("Using preset: Top 10 most traded US stocks (static list).")
    tickers = TOP_10_MOST_TRADED_US

do_analyze = st.button("🚀 Analyze now")

# =========================
# RUN ANALYSIS
# =========================
if do_analyze:
    # record usage at the moment user clicks
    record_usage()

    period, interval = TIMEFRAME_MAP[timeframe_label]

    for ticker in tickers:
        st.subheader(f"📊 {ticker}  ↪")
        df = fetch_price_data(ticker, period=period, interval=interval)

        if df is None or df.empty:
            st.warning("No market data for this ticker.")
            continue

        # we expect a 'Close' column
        if "Close" not in df.columns:
            st.warning("Downloaded data does not contain 'Close' prices.")
            continue

        # ------------- price change / momentum -------------
        latest = float(df["Close"].iloc[-1])
        if len(df) > 1:
            prev = float(df["Close"].iloc[-2])
        else:
            prev = latest
        pct = ((latest - prev) / prev * 100) if prev != 0 else 0.0

        # ------------- show basic stats -------------
        stats_cols = st.columns(3)
        with stats_cols[0]:
            st.metric("Last price", f"${latest:.2f}")
        with stats_cols[1]:
            st.metric("Last candle %", f"{pct:.2f}%")
        with stats_cols[2]:
            st.write(f"Rows: {len(df)}")

        # ------------- chart -------------
        # we'll build a small combined frame with price + volume
        chart_df = df.set_index(df.columns[0])  # datetime index
        # Only keep columns that exist
        keep_cols = []
        if "Close" in chart_df.columns:
            keep_cols.append("Close")
        if "Volume" in chart_df.columns:
            keep_cols.append("Volume")
        if keep_cols:
            st.line_chart(chart_df[keep_cols])
        else:
            st.info("No chartable columns found.")

        # ------------- AI comment -------------
        comment = ai_comment_on_ticker(ticker, pct, latest)
        st.write(f"🧠 {comment}")

        # ------------- CSV export -------------
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label=f"Download {ticker} CSV",
            data=csv,
            file_name=f"{ticker.lower()}_data.csv",
            mime="text/csv",
        )

        st.divider()

else:
    st.info("Select tickers and press **Analyze now** to see data.")
