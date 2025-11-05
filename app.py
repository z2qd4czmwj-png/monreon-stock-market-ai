# app.py — Monreon Stock AI (Gumroad protected)
import streamlit as st
import requests
import pandas as pd
import yfinance as yf
import datetime as dt
from typing import Dict, Any, List

# ===============================
# 1. READ SECRETS / CONFIG
# ===============================
# These should be in your secrets.toml:
# [gumroad]
# ACCESS_TOKEN = "..."
# PRODUCT_ID  = "..."
# [openai]
# OPENAI_API_KEY = "..."
# [app]
# MAX_USES_PER_DAY = "50"

GUMROAD_PRODUCT_ID = st.secrets["gumroad"]["PRODUCT_ID"]
GUMROAD_ACCESS_TOKEN = st.secrets["gumroad"].get("ACCESS_TOKEN", "").strip()
OPENAI_API_KEY = st.secrets.get("openai", {}).get("OPENAI_API_KEY", "")
MAX_USES_PER_DAY = int(st.secrets.get("app", {}).get("MAX_USES_PER_DAY", "50"))

# session keys
SESSION_AUTH = "monreon_auth"
SESSION_DAY = "monreon_day"
SESSION_COUNT = "monreon_count"

# ===============================
# 2. GUMROAD LICENSE VERIFY
# ===============================
def verify_gumroad_license(license_key: str) -> Dict[str, Any]:
    """
    Verifies a license against a specific Gumroad product.
    Uses product_id (the correct way for your product).
    If you added ACCESS_TOKEN, we send it too.
    """
    url = "https://api.gumroad.com/v2/licenses/verify"
    payload: Dict[str, Any] = {
        "product_id": GUMROAD_PRODUCT_ID,
        "license_key": license_key.strip(),
    }
    if GUMROAD_ACCESS_TOKEN:
        payload["access_token"] = GUMROAD_ACCESS_TOKEN

    resp = requests.post(url, data=payload, timeout=10)
    return resp.json()

# ===============================
# 3. DATA HELPERS
# ===============================
TOP_10_US = [
    "AAPL", "TSLA", "NVDA", "MSFT", "AMZN",
    "META", "GOOGL", "AMD", "AVGO", "JPM"
]

def fetch_yf_data(ticker: str, period="6mo", interval="1d") -> pd.DataFrame:
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False)
        if not df.empty:
            return df.dropna(how="all")
    except Exception:
        pass
    return pd.DataFrame()

def calc_momentum(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {"error": "No data"}
    close = df["Close"]
    last = float(close.iloc[-1])
    week = (last - close.iloc[-5]) / close.iloc[-5] * 100 if len(close) > 5 else None
    month = (last - close.iloc[-21]) / close.iloc[-21] * 100 if len(close) > 21 else None
    return {
        "last_price": last,
        "1w_change_pct": week,
        "1m_change_pct": month,
    }

def calc_moving_avgs(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {"error": "No data"}
    close = df["Close"]
    out = {"last_price": float(close.iloc[-1])}
    for win in [5, 20, 50, 100, 200]:
        if len(close) >= win:
            out[f"SMA_{win}"] = float(close.rolling(win).mean().iloc[-1])
    return out

def calc_volatility(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty:
        return {"error": "No data"}
    returns = df["Close"].pct_change().dropna()
    daily = float(returns.std())
    annual = daily * (252 ** 0.5)
    return {"daily_volatility": daily, "annualized_volatility": annual}

def fetch_fundamentals_like(ticker: str) -> Dict[str, Any]:
    try:
        info = yf.Ticker(ticker).fast_info
        return {
            "last_price": info.get("lastPrice"),
            "market_cap": info.get("marketCap"),
            "year_high": info.get("yearHigh"),
            "year_low": info.get("yearLow"),
            "currency": info.get("currency"),
        }
    except Exception:
        return {"error": "Fundamentals unavailable"}

def ai_commentary(ticker: str, metrics: Dict[str, Any], mode: str) -> str:
    if not OPENAI_API_KEY:
        return "AI commentary disabled (no OpenAI key set in Streamlit secrets)."
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        prompt = (
            f"Analyze the stock {ticker} for a trader.\n"
            f"Mode: {mode}\n"
            f"Metrics: {metrics}\n"
            f"Give 3 short, actionable insights and say if sentiment is bullish, bearish, or neutral."
        )
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
            temperature=0.4,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        return f"AI failed: {e}"

# ===============================
# 4. PAGE / SESSION INIT
# ===============================
st.set_page_config(page_title="Monreon Stock AI", layout="wide")

today = dt.date.today().isoformat()
if st.session_state.get(SESSION_DAY) != today:
    st.session_state[SESSION_DAY] = today
    st.session_state[SESSION_COUNT] = 0
if SESSION_AUTH not in st.session_state:
    st.session_state[SESSION_AUTH] = False

# ===============================
# 5. HEADER + LICENSE BOX
# ===============================
st.title("📈 Monreon Stock AI — Advanced Market Scanner")
st.caption("AI-powered stock research • secured with Gumroad license")

if not st.session_state[SESSION_AUTH]:
    st.subheader("🔐 Enter your license to unlock")
    lic = st.text_input("License key from Gumroad", type="password")
    if st.button("Unlock access"):
        data = verify_gumroad_license(lic)
        if data.get("success"):
            st.session_state[SESSION_AUTH] = True
            st.success("✅ License verified. Welcome!")
            st.rerun()
        else:
            # show gumroad’s exact message to help debug
            st.error(data.get("message", "License not valid for this product."))
            st.code(data, language="json")
            st.stop()
    st.stop()

# daily limit
if st.session_state.get(SESSION_COUNT, 0) >= MAX_USES_PER_DAY:
    st.error("You reached today’s usage limit for this license. Try again tomorrow.")
    st.stop()

# ===============================
# 6. MARKET SNAPSHOT
# ===============================
st.markdown("### 🏦 Market Snapshot")
indices = {"S&P 500": "^GSPC", "NASDAQ": "^IXIC", "Dow Jones": "^DJI"}
cols = st.columns(len(indices))
for i, (name, symbol) in enumerate(indices.items()):
    df_idx = fetch_yf_data(symbol, period="5d", interval="1d")
    if not df_idx.empty:
        latest = float(df_idx["Close"].iloc[-1])
prev = float(df_idx["Close"].iloc[-2]) if len(df_idx) > 1 else latest
pct = ((latest - prev) / prev * 100) if prev != 0 else 0
cols[i].metric(name, f"${latest:,.2f}", f"{pct:+.2f}%")
    else:
        cols[i].write(name)
st.divider()

# ===============================
# 7. USER INPUTS
# ===============================
mode = st.radio(
    "Choose input mode:",
    ["Manual tickers", "Top 10 Most Traded US Stocks"],
    horizontal=True,
)

if mode == "Manual tickers":
    tickers_raw = st.text_input("Tickers (comma separated)", "AAPL, TSLA, NVDA")
else:
    tickers_raw = ", ".join(TOP_10_US)
    st.info("Loaded Top 10 automatically")

period_options = {
    "6 months (1d)": ("6mo", "1d"),
    "1 month (1d)": ("1mo", "1d"),
    "5 days (15m)": ("5d", "15m"),
    "1 day (5m)": ("1d", "5m"),
}
col1, col2 = st.columns(2)
with col1:
    period_label = st.selectbox("Timeframe", list(period_options.keys()), index=0)
with col2:
    analysis_mode = st.selectbox(
        "Analysis mode",
        [
            "Find momentum",
            "Check moving averages",
            "Check volatility",
            "Quick fundamentals",
            "AI summary (if OpenAI key)",
        ],
    )
period, interval = period_options[period_label]

run = st.button("🚀 Analyze now", type="primary")

# ===============================
# 8. RUN ANALYSIS
# ===============================
all_rows: List[Dict[str, Any]] = []

if run:
    # count usage for this license
    st.session_state[SESSION_COUNT] = st.session_state.get(SESSION_COUNT, 0) + 1

    tickers = [t.strip().upper() for t in tickers_raw.split(",") if t.strip()]
    for ticker in tickers:
        st.subheader(f"📊 {ticker}")
        df = fetch_yf_data(ticker, period=period, interval=interval)

        # chart section
        if not df.empty:
            cA, cB = st.columns([3, 1])
            with cA:
                st.line_chart(df[["Close"]])
            with cB:
                st.bar_chart(df[["Volume"]].tail(60))
        else:
            st.warning("No market data for this ticker.")
            continue

        # analysis section
        if analysis_mode == "Find momentum":
            metrics = calc_momentum(df)
        elif analysis_mode == "Check moving averages":
            metrics = calc_moving_avgs(df)
        elif analysis_mode == "Check volatility":
            metrics = calc_volatility(df)
        elif analysis_mode == "Quick fundamentals":
            metrics = fetch_fundamentals_like(ticker)
        else:
            metrics = {"last_close": float(df["Close"].iloc[-1])}

        if "error" in metrics:
            st.error(metrics["error"])
        else:
            st.write(metrics)

        # AI commentary
        ai_text = ai_commentary(ticker, metrics, analysis_mode)
        st.info(ai_text)

        # collect for CSV
        row = {
            "ticker": ticker,
            "mode": analysis_mode,
            **metrics,
            "ai_commentary": ai_text,
        }
        all_rows.append(row)

        st.markdown("---")

# ===============================
# 9. CSV EXPORT
# ===============================
if all_rows:
    out_df = pd.DataFrame(all_rows)
    st.download_button(
        "⬇️ Download results as CSV",
        data=out_df.to_csv(index=False).encode("utf-8"),
        file_name="monreon_stock_ai_results.csv",
        mime="text/csv",
    )

st.caption("© 2025 Monreon AI — Licensed for paying customers only. Sharing keys is prohibited.")
