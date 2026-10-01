import os
from dotenv import load_dotenv

load_dotenv()

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

if not GITHUB_TOKEN:
    try:
        import streamlit as st
        GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
    except Exception:
        GITHUB_TOKEN = None

OWNER = "selvamsekar66"
REPOSITORY = "sre-zero-to-hero"

BASE_URL = "https://api.github.com"

HEADERS = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2026-03-10"
}