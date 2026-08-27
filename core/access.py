"""로그인 쿠키·직원 접속 토큰 검증. app.py/pages 에서 호출한다.

부록 A-5(v1 app.py/database.py 발췌) 패턴을 옮긴 것. core/ 의 다른 모듈과 달리
Streamlit 위젯을 직접 그린다 — 인증은 UI 와 분리하기 어려운 관심사이기 때문.
"""

from datetime import datetime, timedelta, timezone

import extra_streamlit_components as stx
import streamlit as st
from supabase import create_client

from core.auth import COOKIE_NAME, DEFAULT_TTL_SECONDS, issue_token, verify_token
from core.db import authenticate_admin, get_owner_by_staff_token
from core.session_keys import LOGGED_IN_USER, STAFF_NICKNAME
from core.settings import get_env

STAFF_NICKNAME_COOKIE = "c2o_live_staff"
STAFF_NICKNAME_TTL_SECONDS = 7 * 24 * 3600  # 7일

_ADMIN_COOKIE_MANAGER_KEY = "admin_cookie_manager"
_STAFF_COOKIE_MANAGER_KEY = "staff_cookie_manager"


@st.cache_resource
def get_db():
    url = get_env("SUPABASE_URL")
    key = get_env("SUPABASE_KEY")
    return create_client(url, key) if url and key else None


def get_admin_cookie_manager() -> stx.CookieManager:
    return stx.CookieManager(key=_ADMIN_COOKIE_MANAGER_KEY)


def require_admin(db) -> str:
    """로그인된 관리자의 user_id 를 반환한다. 실패하면 로그인 폼을 그리고 멈춘다."""
    secret = get_env("AUTH_SECRET")
    cookie_manager = get_admin_cookie_manager()

    if LOGGED_IN_USER not in st.session_state:
        restored = verify_token(cookie_manager.get(COOKIE_NAME), secret)
        if restored:
            st.session_state[LOGGED_IN_USER] = restored

    if LOGGED_IN_USER in st.session_state:
        return st.session_state[LOGGED_IN_USER]

    _render_login_form(db, cookie_manager, secret)
    st.stop()
    raise RuntimeError("unreachable")  # st.stop() 이 스크립트 실행을 여기서 끝낸다


def _render_login_form(db, cookie_manager: stx.CookieManager, secret: str) -> None:
    _, center, _ = st.columns([1, 2, 1])
    with center:
        st.markdown(
            """
            <div style="text-align:center; padding:2rem 0;">
              <h1 style="color:#FF6B35;">Chat2Order Live</h1>
              <p style="color:#888;">로그인하여 시작하세요</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        with st.form("login_form"):
            email = st.text_input("이메일")
            password = st.text_input("비밀번호", type="password")
            submitted = st.form_submit_button("LogIn", width="stretch", type="primary")
        if not submitted:
            return
        if db is None:
            st.error("DB 연결이 설정되지 않았습니다. 관리자에게 문의하세요.")
            return
        if not authenticate_admin(db, email, password):
            st.error("이메일/비밀번호가 올바르지 않거나 비활성화된 계정입니다.")
            return
        st.session_state[LOGGED_IN_USER] = email
        if secret:
            token = issue_token(email, secret)
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=DEFAULT_TTL_SECONDS)
            cookie_manager.set(COOKIE_NAME, token, key="set_auth_cookie", expires_at=expires_at)
        st.rerun()


def logout() -> None:
    st.session_state.pop(LOGGED_IN_USER, None)
    cookie_manager = get_admin_cookie_manager()
    try:
        cookie_manager.delete(COOKIE_NAME, key="delete_auth_cookie")
    except KeyError:
        pass


def require_staff(db) -> tuple[str, str]:
    """URL 토큰으로 소유자를 확정하고, 닉네임 쿠키/입력을 받아 (owner_user_id, staff_name)."""
    token = st.query_params.get("t")
    owner = get_owner_by_staff_token(db, token) if db is not None else None
    if not owner:
        st.error("유효하지 않거나 만료된 링크입니다. 관리자에게 새 링크를 요청하세요.")
        st.stop()
        raise RuntimeError("unreachable")

    cookie_manager = stx.CookieManager(key=_STAFF_COOKIE_MANAGER_KEY)

    if STAFF_NICKNAME not in st.session_state:
        cookie_nickname = cookie_manager.get(STAFF_NICKNAME_COOKIE)
        if cookie_nickname:
            st.session_state[STAFF_NICKNAME] = cookie_nickname

    if STAFF_NICKNAME in st.session_state:
        return owner, st.session_state[STAFF_NICKNAME]

    st.subheader("닉네임을 입력해 주세요")
    with st.form("staff_nickname_form"):
        nickname = st.text_input("닉네임")
        submitted = st.form_submit_button("입장", type="primary")
    if submitted and nickname.strip():
        st.session_state[STAFF_NICKNAME] = nickname.strip()
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=STAFF_NICKNAME_TTL_SECONDS)
        cookie_manager.set(
            STAFF_NICKNAME_COOKIE, nickname.strip(), key="set_staff_cookie", expires_at=expires_at
        )
        st.rerun()
    st.stop()
    raise RuntimeError("unreachable")
