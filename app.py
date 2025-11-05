# app.py — Monreon AI (Gumroad-protected)
from __future__ import annotations
import os
import time
from typing import Dict, Any, List

import streamlit as st
import requests

# =============== PAGE CONFIG ===============
st.set_page_config(
    page_title="Monreon Stock AI",
    page_icon="📈",
    layout="wide",
)

# =============== STYLING ===============
st.markdown(
    """
    <style>
    body, [data-testid="stAppViewContainer"] {
        background: #000000 !important;
    }
    .main .block-container {
        background: #ffffff;
        border-radius: 14px;
        padding: 1.5rem 1.5rem 3rem 1.5rem;
        box-shadow: 0 6px 26px rgba(0,0,0,0.2);
        margin-top: 1.4rem;
    }
    [data-testid="stSidebar"] {
        background: #0A1733 !important;
    }
    [data-testid="stSidebar"] * {
        color: #ffffff !important;
    }
    .stButton>button {
        background: #0A1733 !important;
        color: #ffffff !important;
        border-radius: 999px !important;
        border: 0 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# =============== SECRETS HELPERS ===============
def get_secret(path: str, key: str, default: str = "") -> str:
    """
    Reads from st.secrets[path][key] if available, falls back to env, then default.
    Example: get_secret("gumroad", "PRODUCT_PERMALINK")
    """
    try:
        if path in st.secrets and key in st.secrets[path]:
            return st.secrets[path][key]
    except Exception:
        pass
    return os.getenv(key, default)


# =============== CONFIG FROM SECRETS ===============
GUMROAD_PRODUCT_PERMALINK = get_secret("gumroad", "PRODUCT_PERMALINK", "")
GUMROAD_ACCESS_TOKEN = get_secret("gumroad", "ACCESS_TOKEN", "")

# MAX_USES_PER_DAY can be flat at root (like older version)
MAX_USES_RAW = st.secrets.get("MAX_USES_PER_DAY", "50")
try:
    MAX_USES_PER_DAY = int(MAX_USES_RAW)
except Exception:
    MAX_USES_PER_DAY = 50  # fallback

# =============== LICENSE VERIFY ===============
def verify_gumroad_license(license_key: str) -> Dict[str, Any]:
    """
    Calls Gumroad's /v2/licenses/verify endpoint.
    Returns the full JSON so we can inspect refunded, chargeback, etc.
    """
    if not GUMROAD_PRODUCT_PERMALINK:
        # during dev you can allow access
        return {"success": True, "dev_mode": True}

    url = "https://api.gumroad.com/v2/licenses/verify"
    payload = {
        "product_permalink": GUMROAD_PRODUCT_PERMALINK,
        "license_key": license_key,
        "increment_uses_count": True,
    }
    # if we have access token, add it
    if GUMROAD_ACCESS_TOKEN:
        payload["access_token"] = GUMROAD_ACCESS_TOKEN

    try:
        r = requests.post(url, data=payload, timeout=10)
        j = r.json()
        return j
    except Exception as e:
        return {"success": False, "error": str(e)}


def license_gate():
    """
    Sidebar auth gate. Blocks the rest of the app until valid Gumroad license is provided.
    Also enforces per-day usage in session.
    """
    # init session
    st.session_state.setdefault("is_authed", False)
    st.session_state.setdefault("uses_today", 0)
    st.session_state.setdefault("day_stamp", time.strftime("%Y-%m-%d"))

    # reset daily counter if new day
    today = time.strftime("%Y-%m-%d")
    if st.session_state["day_stamp"] != today:
        st.session_state["day_stamp"] = today
        st.session_state["uses_today"] = 0

    with st.sidebar:
        st.header("🔐 Monreon AI Login")
        st.caption("Enter your Gumroad license key to unlock.")
        lic = st.text_input("License key from Gumroad", type="password")
        btn = st.button("Unlock")

        # show daily usage
        if MAX_USES_PER_DAY > 0:
            st.write(f"Today: {st.session_state['uses_today']} / {MAX_USES_PER_DAY}")

    if st.session_state["is_authed"]:
        return  # already in

    if btn:
        if not lic.strip():
            st.error("Please enter your license key.")
            st.stop()

        result = verify_gumroad_license(lic.strip())
        if not result.get("success"):
            st.error("❌ License not valid for this product. Check you bought the right one.")
            st.stop()

        # extra safety: block refunded / chargeback
        purchase = result.get("purchase", {})
        if purchase.get("refunded") or purchase.get("chargebacked"):
            st.error("❌ This license was refunded or chargebacked.")
            st.stop()

        # save auth
        st.session_state["is_authed"] = True
        st.session_state["license_key"] = lic.strip()
        st.success("✅ License verified. Welcome!")
        st.experimental_rerun()

    # if no button pressed yet -> block app
    if not st.session_state["is_authed"]:
        st.title("Monreon Stock AI")
        st.info("This tool is protected. Enter your Gumroad license key in the sidebar to continue.")
        st.stop()


def check_daily_quota():
    """
    Enforces daily limit stored in session.
    """
    if MAX_USES_PER_DAY <= 0:
        return  # unlimited

    used = st.session_state.get("uses_today", 0)
    if used >= MAX_USES_PER_DAY:
        st.error("You have reached today's usage limit. Please come back tomorrow.")
        st.stop()


def count_use():
    st.session_state["uses_today"] = st.session_state.get("uses_today", 0) + 1


# =============== RUN AUTH GATE FIRST ===============
license_gate()

# =============== MAIN APP (after auth) ===============
st.title("📈 Monreon Stock AI — Market Scanner")
st.caption("AI-powered stock research. Licensed version.")

# check daily usage
check_daily_quota()

# simple input UI
tickers_raw = st.text_input("Enter tickers (comma separated)", "AAPL, TSLA, NVDA")
purpose = st.selectbox("What do you want?", ["Quick health check", "Find momentum", "AI summary"])

# when user clicks generate/analyze
if st.button("Analyze now"):
    count_use()  # increase usage
    tickers = [t.strip().upper() for t in tickers_raw.split(",") if t.strip()]
    if not tickers:
        st.warning("Please enter at least one ticker.")
    else:
        st.subheader("Scan Result")
        for t in tickers:
            st.markdown(f"**{t}**")
            st.write("- Recent price: (fetch with yfinance or your data source)")
            st.write("- AI opinion: This is where you'd add OpenAI analysis.")
            st.write("---")

st.markdown(
    """
    <p style="font-size:11px; margin-top:2rem; color:#666;">
    © 2025 Monreon AI. Licensed for personal/client use only. Redistribution or sharing of license keys is prohibited.
    </p>
    """,
    unsafe_allow_html=True,
)
