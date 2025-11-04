import os
import time
import requests
import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf

# ===============================
# 🔐 CONFIG & SECRETS
# ===============================
def get_secret(section: str, key: str, default: str = "") -> str:
    if section in st.secrets and key in st.secrets[section]:
        return st.secrets[section][key]
    return os.getenv(key, default)

GUMROAD_PERMALINK = get_secret("gumroad", "GUMROAD_PRODUCT_PERMALINK", "")
APP_TITLE = "📈 Monreon Stock AI — Market Intelligence Scanner"

# ===============================
# 🔒 LICENSE VALIDATION
# ===============================
def verify_gumroad_license(email: str, license_key: str) -> bool:
    if not license_key or not email or not GUMROAD_PERMALINK:
        return False
    url = "https://api.gumroad.com/v2/licenses/verify"
    payload = {
        "product_permalink": GUMROAD_PERMALINK,
        "license_key": license_key,
        "increment_uses_count": True
    }
    try:
        r = requests.post(url, data=payload, timeout=10)
        d = r.json()
        return d.get("success") and d.get("purchase", {}).get("email", "").lower() == email.lower()
    except Exception:
        return False

# ===============================
# ⚙️ STOCK UNIVERSE
# ===============================
TOP_TECH = [
    "AAPL", "MSFT", "NVDA", "META", "GOOGL", "AMZN", "TSLA", "AVGO",
    "AMD", "ADBE", "CRM", "NFLX", "COST", "PEP", "INTC", "CSCO",
    "TXN", "QCOM", "NOW", "ORCL", "SHOP", "UBER", "SNOW", "PANW",
    "PLTR", "ABNB", "MRNA", "SPOT", "BA", "NKE"
]

# ===============================
# 📊 METRICS & ANALYSIS
# ===============================
def download_data(tickers, period="10d"):
    data = {}
    for t in tickers:
        try:
            df = yf.download(t, period=period, interval="1d", progress=False)
            if not df.empty:
                data[t] = df
        except Exception:
            pass
        time.sleep(0.1)
    return data

def analyze_data(data):
    """
    Compute momentum, volatility, and trend strength
    """
    rows = []
    for t, df in data.items():
        df = df.dropna()
        if len(df) < 3:
            continue
        closes = df["Close"]
        start, last = closes.iloc[0], closes.iloc[-1]
        momentum = (last / start - 1) * 100
        volatility = closes.pct_change().std() * 100
        avg_volume = df["Volume"].mean()
        trend_strength = momentum / (volatility + 1e-6)
        rows.append({
            "Ticker": t,
            "Start Price": round(start, 2),
            "Last Price": round(last, 2),
            "Momentum %": round(momentum, 2),
            "Volatility %": round(volatility, 2),
            "Trend Strength": round(trend_strength, 2),
            "Avg Volume": round(avg_volume / 1e6, 2)
        })
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["Score"] = (
        df["Momentum %"] * 0.6 +
        (100 - df["Volatility %"]) * 0.2 +
        df["Trend Strength"] * 0.2
    )
    return df.sort_values("Score", ascending=False).reset_index(drop=True)

# ===============================
# 🎨 STREAMLIT UI
# ===============================
st.set_page_config(page_title=APP_TITLE, layout="wide")
st.markdown(
    f"<h1 style='text-align:center; color:#57a6ff;'>{APP_TITLE}</h1>",
    unsafe_allow_html=True
)

with st.sidebar:
    st.title("🔒 License Access")
    email = st.text_input("Customer email (same as Gumroad)")
    key = st.text_input("License key", type="password")
    unlock = st.button("Unlock App")

    st.markdown("---")
    st.caption("💡 You’ll receive your key automatically after purchase on Gumroad.")
    st.markdown("[Go to Monreon Gumroad →](https://monreon.gumroad.com)")

if "auth" not in st.session_state:
    st.session_state.auth = False

if unlock:
    with st.spinner("Verifying license..."):
        if verify_gumroad_license(email.strip(), key.strip()):
            st.session_state.auth = True
            st.sidebar.success("✅ License verified! Welcome to Monreon Elite.")
        else:
            st.session_state.auth = False
            st.sidebar.error("❌ Invalid license. Check email/key.")

if not st.session_state.auth:
    st.warning("Please unlock with your Gumroad license to start scanning the market.")
    st.stop()

# ===============================
# ✅ MAIN APP
# ===============================
st.success("✅ License verified — scanning market data in real time.")

col1, col2, col3 = st.columns([2, 2, 1])
with col1:
    universe_mode = st.selectbox(
        "Choose universe",
        ["Top Tech 30", "Custom tickers"]
    )
with col2:
    lookback = st.slider("Lookback days", 3, 20, 7)
with col3:
    st.write("")
    start_btn = st.button("🚀 Run Scanner", use_container_width=True)

if universe_mode == "Top Tech 30":
    tickers = TOP_TECH
else:
    tickers = [x.strip().upper() for x in st.text_area(
        "Paste your custom tickers (comma separated)", "AAPL, MSFT, TSLA").split(",") if x.strip()]

if start_btn:
    st.markdown("### ⏱️ Fetching & analyzing market data...")
    with st.spinner("Downloading recent data and calculating performance metrics..."):
        data = download_data(tickers, period=f"{lookback}d")
        result = analyze_data(data)

    if result.empty:
        st.error("No valid data received. Try fewer or valid tickers.")
    else:
        st.markdown("## 🔥 Top Momentum & Trend Stocks")
        st.dataframe(result.head(15), use_container_width=True)

        # Highlight strongest
        top = result.head(3)
        insights = []
        for i, r in top.iterrows():
            insights.append(
                f"**{r['Ticker']}** is up **{r['Momentum %']}%** with strong trend strength ({r['Trend Strength']:.2f}) and steady volume ({r['Avg Volume']}M avg)."
            )
        st.markdown("### 🧠 AI-Style Insights")
        st.markdown("\n".join(insights))
        st.info("Combine these signals with your own technical indicators and strategy. Data updates daily via Yahoo Finance.")

        # Chart visualization for top
        pick = st.selectbox("Select a stock to visualize", result["Ticker"].head(10))
        if pick in data:
            st.line_chart(data[pick]["Close"], use_container_width=True)
else:
    st.info("Click **🚀 Run Scanner** to start scanning the market.")
