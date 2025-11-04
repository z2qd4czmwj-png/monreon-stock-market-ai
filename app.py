import os
import time
from typing import List, Dict, Any

import streamlit as st
import pandas as pd
import yfinance as yf

# =========================
# SECRETS / CONFIG
# =========================
def get_secret(section: str, key: str, default: str = "") -> str:
    """Safe getter for streamlit secrets."""
    if section in st.secrets and key in st.secrets[section]:
        return st.secrets[section][key]
    return os.getenv(key, default)

PAYHIP_SECRET = get_secret("payhip", "SECRET_KEY", "")
OPENAI_API_KEY = get_secret("payhip", "OPENAI_API_KEY", "")  # optional – only if you want GPT analysis


# =========================
# PAYHIP LICENSE CHECK
# =========================
def verify_payhip_license(secret_key: str, license_key: str, customer_email: str) -> bool:
    """
    Very simple placeholder verifier.
    Real Payhip verification = call their API with secret key + license.
    Here we just check that user typed something and that we have our secret.
    """
    if not secret_key:
        return False
    if not license_key:
        return False
    # You can add real API call here later.
    return True


# =========================
# STOCK UNIVERSE
# =========================
# You said “all possible stocks” — but that’s huge.
# For now we scan a starter universe. You can grow this list later
# or load it from a Google Sheet.
DEFAULT_UNIVERSE = [
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN",
    "META", "TSLA", "AMD", "AVGO", "NFLX",
    "JPM", "V", "MA", "ADBE", "COST",
    "UNH", "PEP", "KO", "ORCL", "INTC"
]


# =========================
# DATA HELPERS
# =========================
@st.cache_data(ttl=300)
def get_stock_snapshot(ticker: str) -> Dict[str, Any]:
    """
    Pulls quick data for a ticker.
    Returns price, 52w high/low, and simple momentum.
    """
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="6mo")
        info = t.fast_info  # faster than .info
        if hist.empty:
            return {}

        last_price = float(hist["Close"].iloc[-1])
        first_price = float(hist["Close"].iloc[0])
        pct_change_6m = (last_price - first_price) / first_price * 100

        # 52 week data
        high_52w = getattr(info, "year_high", None)
        low_52w = getattr(info, "year_low", None)

        return {
            "ticker": ticker,
            "price": last_price,
            "pct_change_6m": pct_change_6m,
            "52w_high": high_52w,
            "52w_low": low_52w,
        }
    except Exception:
        return {}


def score_stock(row: Dict[str, Any]) -> float:
    """
    Very simple scoring: higher 6M momentum gets higher score.
    You can improve this later (volume, RSI, EPS surprises, news sentiment…)
    """
    if not row:
        return 0.0
    score = 0.0
    # momentum
    score += max(min(row.get("pct_change_6m", 0) / 5, 10), -10)
    # proximity to 52w high
    price = row.get("price")
    high_52w = row.get("52w_high")
    if price and high_52w:
        dist = (high_52w - price) / high_52w * 100
        if dist < 10:  # near breakout
            score += 2
    return round(score, 2)


def scan_universe(tickers: List[str]) -> pd.DataFrame:
    results = []
    for tk in tickers:
        snap = get_stock_snapshot(tk)
        if snap:
            snap["score"] = score_stock(snap)
            results.append(snap)
        time.sleep(0.1)  # be nice to yfinance
    if not results:
        return pd.DataFrame()
    df = pd.DataFrame(results)
    df = df.sort_values("score", ascending=False)
    return df


# =========================
# UI
# =========================
st.set_page_config(
    page_title="Monreon Stock AI",
    page_icon="📈",
    layout="wide",
)

st.title("📈 Monreon Stock AI — Market Scanner")
st.write("Scan a list of stocks, score them, and show buyers only if they have a valid Payhip license.")

# ---- LICENSE GATE ----
with st.sidebar:
    st.header("🔐 License check")
    email_input = st.text_input("Customer email (same as Payhip)", "")
    license_input = st.text_input("License key", type="password")
    st.caption("You get this automatically after buying on Payhip.")

    if st.button("Unlock tool"):
        if verify_payhip_license(PAYHIP_SECRET, license_input, email_input):
            st.session_state["license_ok"] = True
            st.success("License verified ✅")
        else:
            st.session_state["license_ok"] = False
            st.error("License invalid ❌")

# Check license state
if not st.session_state.get("license_ok", False):
    st.warning("This tool is locked. Enter your Payhip email + license key in the sidebar to unlock.")
    st.stop()

# ---- MAIN TOOL ----
st.success("Access granted ✅")

col1, col2 = st.columns(2)
with col1:
    st.subheader("1. Choose stock universe")
    mode = st.radio(
        "Scan mode",
        ["Use default list (Top US tech & large caps)", "I will paste my own tickers"],
    )

with col2:
    st.subheader("2. Scan options")
    top_n = st.slider("How many top ideas to show?", 5, 50, 15)

# get tickers
if mode == "Use default list (Top US tech & large caps)":
    tickers_to_scan = DEFAULT_UNIVERSE
    st.info(f"📦 Using built-in list of {len(DEFAULT_UNIVERSE)} tickers.")
else:
    user_tickers = st.text_area(
        "Paste tickers separated by commas (e.g. AAPL, TSLA, NVDA, MSFT)",
        "",
    )
    tickers_to_scan = [t.strip().upper() for t in user_tickers.split(",") if t.strip()]
    st.info(f"📦 You provided {len(tickers_to_scan)} tickers.")

if st.button("🚀 Run market scan"):
    if not tickers_to_scan:
        st.error("Please provide at least 1 ticker.")
    else:
        with st.spinner("Scanning market and ranking opportunities…"):
            df = scan_universe(tickers_to_scan)
        if df.empty:
            st.error("Could not fetch any data. Try fewer tickers or later.")
        else:
            st.success(f"Found {len(df)} stocks. Showing best {top_n}.")
            st.dataframe(df.head(top_n), use_container_width=True)

            # quick download
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Download full results as CSV",
                csv,
                "monreon-stock-scan.csv",
                "text/csv",
            )

            st.markdown("##### How scores work")
            st.markdown(
                "- Based on 6-month momentum\n"
                "- Small bonus if price is near 52-week high\n"
                "- You can later plug GPT here to generate written insights per ticker"
            )

# =========================
# OPTIONAL: AI EXPLANATION (if you set OPENAI_API_KEY in secrets)
# =========================
if OPENAI_API_KEY:
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)

    st.subheader("🧠 AI insight (optional)")
    picked = st.text_input("Type a ticker from the table to get AI insight", "AAPL")
    if st.button("Generate AI insight"):
        prompt = f"Give me a SHORT, non-investment-advice overview of the stock {picked}. Mention recent momentum, and what a trader might look for."
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=250,
        )
        st.write(resp.choices[0].message.content)
else:
    st.info("Add your OPENAI_API_KEY to Streamlit secrets if you want AI text insights.")
