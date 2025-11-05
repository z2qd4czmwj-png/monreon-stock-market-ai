import streamlit as st
import requests
import pandas as pd
import yfinance as yf
import datetime as dt
from typing import Dict, Any, List

# ===============================
# 1. CONFIG / SECRETS
# ===============================
# You can set EITHER of these in Streamlit secrets:
# GUMROAD_PRODUCT_ID = "xxxx"          ← newer method
# GUMROAD_PRODUCT_PERMALINK = "aikbve" ← what you have now
GUMROAD_PRODUCT_ID = st.secrets.get("GUMROAD_PRODUCT_ID", "").strip()
GUMROAD_PRODUCT_PERMALINK = st.secrets.get("GUMROAD_PRODUCT_PERMALINK", "").strip()

OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY", "").strip()
MAX_USES_PER_DAY = int(st.secrets.get("MAX_USES_PER_DAY", 50))

SESSION_AUTH = "monreon_auth"
SESSION_DAY = "monreon_day"
SESSION_COUNT = "monreon_count"

# ===============================
# 2. LICENSE VERIFY (ID → else permalink)
# ===============================
def verify_gumroad_license(license_key: str) -> Dict[str, Any]:
    """
    Tries to verify with product_id first.
    If you haven't got product_id, it falls back to product_permalink.
    """
    url = "https://api.gumroad.com/v2/licenses/verify"
    payload: Dict[str, Any] = {
        "license_key": license_key.strip(),
    }

    if GUMROAD_PRODUCT_ID:
        payload["product_id"] = GUMROAD_PRODUCT_ID
    elif GUMROAD_PRODUCT_PERMALINK:
        payload["product_permalink"] = GUMROAD_PRODUCT_PERMALINK
    else:
        return {"success": False, "message": "No Gumroad product_id or product_permalink set."}

    try:
        resp = requests.post(url, data=payload, timeout=10)
        return resp.json()
    except Exception as e:
        return {"success": False, "message": f"Request failed: {e}"}

# ===============================
# 3. STOCK HELPERS
# ===============================
TOP_10_US = [
    "AAPL","TSLA","NVDA","MSFT","AMZN",
    "META","GOOGL","AMD","AVGO","JPM"
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
    if df.empty: return {"error": "No data"}
    close = df["Close"]
    last = float(close.iloc[-1])
    week = (last - close.iloc[-5]) / close.iloc[-5] * 100 if len(close) > 5 else None
    month = (last - close.iloc[-21]) / close.iloc[-21] * 100 if len(close) > 21 else None
    return {"last_price": last, "1w_change_pct": week, "1m_change_pct": month}

def calc_moving_avgs(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty: return {"error": "No data"}
    close = df["Close"]
    out = {"last_price": float(close.iloc[-1])}
    for win in [5, 20, 50, 100, 200]:
        if len(close) >= win:
            out[f"SMA_{win}"] = float(close.rolling(win).mean().iloc[-1])
    return out

def calc_volatility(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty: return {"error": "No data"}
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
        return "AI commentary disabled (no OPENAI_API_KEY set)."
    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)
        prompt = (
            f"Analyze stock {ticker} for a trader. Mode: {mode}. "
            f"Metrics: {metrics}. Give 3 insights and a sentiment."
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
# 4. PAGE INIT
# ===============================
st.set_page_config(page_title="Monreon Stock AI", layout="wide")

today = dt.date.today().isoformat()
if st.session_state.get(SESSION_DAY) != today:
    st.session_state[SESSION_DAY] = today
    st.session_state[SESSION_COUNT] = 0
if SESSION_AUTH not in st.session_state:
    st.session_state[SESSION_AUTH] = False

# ===============================
# 5. HEADER + LOGIN (center)
# ===============================
st.title("📈 Monreon Stock AI — Advanced Market Scanner")
st.caption("AI-powered stock research • Gumroad license protected")

if not st.session_state[SESSION_AUTH]:
    st.subheader("🔐 Unlock your tool")
    lic = st.text_input("Enter the license key from Gumroad", type="password")
    if st.button("Unlock access"):
        res = verify_gumroad_license(lic)
        if res.get("success"):
            st.session_state[SESSION_AUTH] = True
            st.success("✅ License verified — welcome!")
            st.rerun()
        else:
            st.error(res.get("message", "License not valid."))
            # show raw for debugging
            st.code(res, language="json")
            st.stop()
    st.stop()

# daily limit
if st.session_state.get(SESSION_COUNT, 0) >= MAX_USES_PER_DAY:
    st.error("Daily limit reached for this license. Try again tomorrow.")
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
        latest = df_idx["Close"].iloc[-1]
        prev = df_idx["Close"].iloc[-2] if len(df_idx) > 1 else latest
        pct = (latest - prev) / prev * 100 if prev else 0
        cols[i].metric(name, f"${latest:,.2f}", f"{pct:+.2f}%")
    else:
        cols[i].write(name)
st.divider()

# ===============================
# 7. INPUTS
# ===============================
input_mode = st.radio("Choose input mode:", ["Manual input", "Top 10 Most Traded US Stocks"], horizontal=True)

if input_mode == "Manual input":
    tickers_raw = st.text_input("Tickers (comma separated)", "AAPL, TSLA, NVDA")
else:
    tickers_raw = ", ".join(TOP_10_US)
    st.info("Loaded Top 10 most traded US stocks.")

period_options = {
    "6 months (1d)": ("6mo", "1d"),
    "1 month (1d)": ("1mo", "1d"),
    "5 days (15m)": ("5d", "15m"),
    "1 day (5m)": ("1d", "5m"),
}
c1, c2 = st.columns(2)
with c1:
    period_label = st.selectbox("Timeframe", list(period_options.keys()), index=0)
with c2:
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
# 8. ANALYSIS
# ===============================
rows: List[Dict[str, Any]] = []

if run:
    st.session_state[SESSION_COUNT] = st.session_state.get(SESSION_COUNT, 0) + 1

    tickers = [t.strip().upper() for t in tickers_raw.split(",") if t.strip()]
    for ticker in tickers:
        st.subheader(f"📊 {ticker}")
        df = fetch_yf_data(ticker, period=period, interval=interval)

        # price + volume chart
        if not df.empty:
            cA, cB = st.columns([3, 1])
            with cA:
                st.line_chart(df[["Close"]])
            with cB:
                st.bar_chart(df[["Volume"]].tail(60))
        else:
            st.warning("No data for this ticker.")
            continue

        # analysis
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

        rows.append({
            "ticker": ticker,
            "mode": analysis_mode,
            **metrics,
            "ai_commentary": ai_text,
        })

        st.markdown("---")

# ===============================
# 9. CSV EXPORT
# ===============================
if rows:
    df_out = pd.DataFrame(rows)
    st.download_button(
        "⬇️ Download results as CSV",
        data=df_out.to_csv(index=False).encode("utf-8"),
        file_name="monreon_stock_ai_results.csv",
        mime="text/csv",
    )

st.caption("© 2025 Monreon AI — Licensed for buyers only.")
