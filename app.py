from pathlib import Path

import streamlit as st
from supabase import create_client

from core.settings import get_env

st.set_page_config(page_title="Chat2Order Live", page_icon="📦", layout="wide")

_css_path = Path(__file__).parent / "styles" / "main.css"
st.markdown(f"<style>{_css_path.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


@st.cache_resource
def get_db():
    url = get_env("SUPABASE_URL")
    key = get_env("SUPABASE_KEY")
    return create_client(url, key) if url and key else None


admin_page = st.Page("pages/admin.py", title="관리자", url_path="")
order_page = st.Page("pages/order.py", title="주문 입력", url_path="order")
search_page = st.Page("pages/search.py", title="주문 검색", url_path="search")

nav = st.navigation([admin_page, order_page, search_page], position="hidden")
nav.run()
