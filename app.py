import os
import time
import datetime as dt
from typing import Dict, Any, List

import streamlit as st
import pandas as pd
import yfinance as yf
import requests

# =========================================================
# 1) SAFE SECRETS GETTER
# =========================================================
def get_secret(section: str, key: str, default: str = "") -> str:
    """Read from streamlit secrets if present, otherwise env, otherwise default."""
    try:
        if section in st.secrets and key in st.secrets[section]:
            return st.secrets[section][key]
    except Exception:
        pass
    return os.getenv(key, default)


# =========================================================
# 2) CONFIG FROM SECRETS
# =========================================================
GUMROAD_PRODUCT_PERMALINK = get_secret("gumroad", "PRODUCT_PERMALINK", "")
GUMROAD_ACCESS_TOKEN = get_secret("gumroad", "ACCESS_TOKEN", "")
OPENAI_API_KEY = get_secret("openai", "OPENAI_API_KEY", "")
MAX_USES_PER_DAY = int(get_secret("app", "MAX_USES_PER_DAY", "50"))  # daily per key

# session key names
SESSION_AUTH_OK = "monreon_auth_ok"
SESSION_LICENSE = "monreon_license"
SESSION_TODAY_COUNT = "monreon_today_count"
SESSION_TODAY_DATE = "monreon_today_date"

# =========================================================
# 3) GUMROAD VERIFY FUNCTION
# =========================================================
def verify_gumroad_license(license_key: str) -> Dict[str, Any]:
    """
    Calls Gumroad's /v2/licenses/verify.
    We need at least: product_permalink + license_key.
    access_token is optional but good.
    """
    url = "https://api.gumroad.com/v2/licenses/verify"
    payload = {
        "product_permalink": GUMROAD_PRODUCT_PERMALINK,
        "license_key": license_key.strip(),
    }
    if GUMROAD_ACCESS_TOKEN:
        payload["access_token"] = GUMROAD_ACCESS_TOKEN

    try:
        resp = requests.post(url, data=payload, timeout=10)
        data = resp.json()
        return data
    except Exception as e:
        return {"success": False, "message": f"Request failed: {e}"}


# =========================================================
# 4) LICENSE GATE UI
# =========================================================
def license_gate():
    """Shows the sidebar login and enforces daily usage limit."""
    # init session vars
    today_str = dt.date.today().isoformat()
    if SESSION_TODAY_DATE not in st.session_state:
        st.session_state[SESSION_TODAY_DATE] = today_str
    if st.session_state.get(SESSION_TODAY_DATE) != today_str:
        # new day -> reset count
        st.session_state[SESSION_TODAY_DATE] = today_str
        st.session_state[SESSION_TODAY_COUNT] = 0
    if SESSION_TODAY_COUNT not in st.session_state:
        st.session_state[SESSION_TODAY_COUNT] = 0

    with st.sidebar:
        st.markdown("🔐 **Monreon AI Login**")
        if not GUMROAD_PRODUCT_PERMALINK:
            st.error("Missing Gumroad product permalink in secrets.\n\nAdd:\n[gumroad]\nPRODUCT_PERMALINK = \"yourcode\"")
        license_key = st.text_input("License key from Gumroad", type="password")
        st.write(f"Today: {st.session_state[SESSION_TODAY_COUNT]} / {MAX_USES_PER_DAY}")
        if st.button("Unlock"):
            if not license_key:
                st.warning("Enter a license key.")
            else:
                data = verify_gumroad_license(license_key)
                if data.get("success"):
                    # You could also check "uses" or "chargebacked" here
                    st.session_state[SESSION_AUTH_OK] = True
                    st.session_state[SESSION_LICENSE] = license_key
                    st.success("License verified. Welcome!")
                    st.rerun()
                else:
                    msg = data.get("message", "License not valid.")
                    st.error(msg)

    # now enforce limit + auth
    if not st.session_state.get(SESSION_AUTH_OK, False):
        st.stop()

    # daily usage limit
    if st.session_state[SESSION_TODAY_COUNT] >= MAX_USES_PER_DAY:
        st.error("Daily limit reached for this key.")
        st.stop()


# =========================================================
# 5) STOCK HELPERS
# =========================================================
TOP_US_PRESET = [
    "AAPL", "TSLA", "NVDA", "MSFT", "AMZN", "META",
    "GOOGL", "AMD", "AVGO", "JPM"
]

def fetch_yf_data(ticker: str, period: str = "6mo", interval: str = "1d") -> pd.DataFrame:
    try:
        df = yf.download(ticker, period=period, interval=interval, progress=False)
        if isinstance(df, pd.DataFrame) and not df.empty:
            df.dropna(how="all", inplace=True)
        return df
    except Exception:
        return pd.DataFrame()


def analyze_ticker(ticker: str) -> Dict[str, Any]:
    """
    Returns a small dict with info we can show.
    You can grow this later (RSI, MA crossover, etc.)
    """
    ticker = ticker.upper().strip()
    info: Dict[str, Any] = {"ticker": ticker, "ok": False}

    df = fetch_yf_data(ticker, period="6mo", interval="1d")
    if df.empty:
        info["reason"] = "No data from yfinance"
        return info

    # simple signals
    close = df["Close"].iloc[-1]
    info["last_price"] = float(close)

    # momentum: last close vs 20d avg
    last_20 = df["Close"].tail(20)
    info["ma20"] = float(last_20.mean())
    info["momentum"] = "bullish" if close > last_20.mean() else "neutral/weak"

    # volume snapshot
    info["last_volume"] = int(df["Volume"].iloc[-1])
    info["avg_volume_20"] = int(df["Volume"].tail(20).mean())

    info["ok"] = True
    return info


def build_dataframe(results: List[Dict[str, Any]]) -> pd.DataFrame:
    rows = []
    for r in results:
        if not r.get("ok"):
            rows.append({
                "ticker": r.get("ticker"),
                "status": r.get("reason", "no data"),
            })
        else:
            rows.append({
                "ticker": r["ticker"],
                "price": r["last_price"],
                "ma20": r["ma20"],
                "momentum": r["momentum"],
                "last_volume": r["last_volume"],
                "avg_volume_20": r["avg_volume_20"],
            })
    return pd.DataFrame(rows)


# =========================================================
# 6) MAIN APP
# =========================================================
def main():
    st.set_page_config(page_title="Monreon Stock AI — Market Scanner", layout="wide")

    # 1) gate
    license_gate()

    # if we passed gate, increase daily counter when user actually scans
    st.title("📈 Monreon Stock AI — Market Scanner")
    st.caption("AI-style stock research (licensed through Gumroad).")

    left, right = st.columns([2, 1])

    with right:
        st.markdown("### 🔁 Quick presets")
        if st.button("Top 10 US today"):
            st.session_state["tickers_input"] = ", ".join(TOP_US_PRESET)
        if st.button("Only big tech"):
            st.session_state["tickers_input"] = "AAPL, MSFT, AMZN, META, GOOGL"
        if st.button("Semiconductors"):
            st.session_state["tickers_input"] = "NVDA, AMD, AVGO, ASML"

        st.markdown("---")
        st.markdown("### Export")
        if "last_df" in st.session_state:
            csv = st.session_state["last_df"].to_csv(index=False).encode("utf-8")
            st.download_button("Download latest scan as CSV", csv, "monreon_scan.csv", "text/csv")

        st.markdown("---")
        st.markdown("### Info")
        st.write(f"🔑 License: {st.session_state.get(SESSION_LICENSE, '')[:6]}•••")
        st.write(f"📅 Today used: {st.session_state[SESSION_TODAY_COUNT]} / {MAX_USES_PER_DAY}")

    with left:
        # user input
        default_tickers = st.session_state.get("tickers_input", "AAPL, TSLA, NVDA")
        tickers_str = st.text_input("Enter tickers (comma separated)", value=default_tickers)
        st.session_state["tickers_input"] = tickers_str

        scan_mode = st.selectbox(
            "What do you want?",
            [
                "Find momentum",
                "Check volume vs average",
                "Simple price snapshot",
                "Full scan (slower)",
            ],
        )

        col_a, col_b, col_c = st.columns(3)
        with col_a:
            period = st.selectbox("History period", ["1mo", "3mo", "6mo", "1y"], index=2)
        with col_b:
            interval = st.selectbox("Interval", ["1d", "1h", "30m", "15m"], index=0)
        with col_c:
            chart_ticker = st.text_input("Chart a single ticker", value="AAPL")

        if st.button("Analyze now", type="primary"):
            # charge 1 use
            st.session_state[SESSION_TODAY_COUNT] += 1

            tickers = [t.strip().upper() for t in tickers_str.split(",") if t.strip()]
            results = []
            with st.spinner("Scanning..."):
                for t in tickers:
                    res = analyze_ticker(t)
                    results.append(res)
                    # tiny sleep just to be nice to yfinance
                    time.sleep(0.1)

            df = build_dataframe(results)
            st.session_state["last_df"] = df

            st.subheader("Scan Result")
            st.dataframe(df, use_container_width=True)

            # show AI-ish interpretation per ticker
            for r in results:
                st.markdown("---")
                st.markdown(f"#### {r.get('ticker')}")
                if not r.get("ok"):
                    st.warning(r.get("reason", "No data"))
                    continue

                price = r["last_price"]
                ma20 = r["ma20"]
                mom = r["momentum"]
                vol = r["last_volume"]
                vol_avg = r["avg_volume_20"]

                st.write(f"• Recent price: **{price:.2f}**")
                st.write(f"• 20-day average: **{ma20:.2f}**")
                st.write(f"• Momentum signal: **{mom}**")
                st.write(f"• Volume last vs avg20: **{vol} vs {vol_avg}**")

                # lightweight "AI" text
                notes = []
                if price > ma20:
                    notes.append("price is trading above short-term average")
                if vol > vol_avg * 1.3:
                    notes.append("volume spike detected")
                if mom == "bullish":
                    notes.append("bullish structure in short window")

                if notes:
                    st.info("AI notes: " + "; ".join(notes))
                else:
                    st.info("AI notes: normal conditions.")

        # chart section
        st.markdown("---")
        st.subheader("Price chart")
        chart_df = fetch_yf_data(chart_ticker.upper().strip(), period=period, interval=interval)
        if not chart_df.empty:
            st.line_chart(chart_df["Close"], height=240)
            st.caption("Close price")
            # small volume table
            vol_df = chart_df[["Volume"]].tail(30)
            st.bar_chart(vol_df, height=160)
            st.caption("Recent volume")
        else:
            st.write("No data for that ticker.")


if __name__ == "__main__":
    main()
