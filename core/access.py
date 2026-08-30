"""로그인 쿠키·직원 접속 토큰 검증. app.py/pages 에서 호출한다.

부록 A-5(v1 app.py/database.py 발췌) 패턴을 옮긴 것. core/ 의 다른 모듈과 달리
Streamlit 위젯을 직접 그린다 — 인증은 UI 와 분리하기 어려운 관심사이기 때문.
"""

from datetime import datetime, timedelta, timezone
from urllib.parse import unquote

import extra_streamlit_components as stx
import streamlit as st

from core.auth import COOKIE_NAME, DEFAULT_TTL_SECONDS, issue_token, verify_token
from core.db import authenticate_admin, get_gemini_api_key, get_owner_by_staff_token
from core.session_keys import (
    AUTH_COOKIE_CHECKED,
    AUTH_COOKIE_CLEAR_PENDING,
    GEMINI_API_KEY,
    LOGGED_IN_USER,
    STAFF_COOKIE_CHECKED,
    STAFF_NICKNAME,
)
from core.settings import get_env
from core.supabase_client import create_supabase_client

STAFF_NICKNAME_COOKIE = "c2o_live_staff"
STAFF_NICKNAME_TTL_SECONDS = 7 * 24 * 3600  # 7일

_ADMIN_COOKIE_MANAGER_KEY = "admin_cookie_manager"
_STAFF_COOKIE_MANAGER_KEY = "staff_cookie_manager"


@st.cache_resource
def get_db():
    url = get_env("SUPABASE_URL")
    key = get_env("SUPABASE_KEY")
    return create_supabase_client(url, key) if url and key else None


def get_admin_cookie_manager() -> stx.CookieManager:
    return stx.CookieManager(key=_ADMIN_COOKIE_MANAGER_KEY)


def read_request_cookie(name: str) -> str | None:
    """세션 최초 요청 헤더에서 쿠키 값을 동기적으로 읽는다.

    ``stx.CookieManager.get()`` 은 iframe 이 마운트된 뒤에야 값을 돌려주므로 첫 렌더에서는
    항상 ``None`` 이다. 그 값을 믿고 로그인 폼을 그리면, 사용자가 이메일을 입력하는 도중
    컴포넌트 응답이 도착하며 rerun 이 걸려 쿠키에 남아있던 계정으로 로그인돼 버린다.
    ``st.context.cookies`` 는 요청 헤더에서 읽으므로 첫 렌더부터 값이 있어 이 경합이 없다.
    쿠키 값은 브라우저 측에서 percent-encoding 되어 저장되므로 디코딩해서 돌려준다.
    """
    try:
        raw = st.context.cookies.get(name)
    except Exception:  # pragma: no cover - 컨텍스트가 없는 실행 경로 방어
        return None
    return unquote(raw) if raw else None


def require_admin(db) -> str:
    """로그인된 관리자의 user_id 를 반환한다. 실패하면 로그인 폼을 그리고 멈춘다."""
    secret = get_env("AUTH_SECRET")

    if LOGGED_IN_USER not in st.session_state and not st.session_state.get(AUTH_COOKIE_CHECKED):
        st.session_state[AUTH_COOKIE_CHECKED] = True
        restored = verify_token(read_request_cookie(COOKIE_NAME), secret)
        if restored:
            st.session_state[LOGGED_IN_USER] = restored

    if LOGGED_IN_USER in st.session_state:
        _ensure_gemini_key_cached(db, st.session_state[LOGGED_IN_USER])
        return st.session_state[LOGGED_IN_USER]

    cookie_manager = get_admin_cookie_manager()
    if st.session_state.pop(AUTH_COOKIE_CLEAR_PENDING, False):
        _delete_auth_cookie(cookie_manager)
    _render_login_form(db, cookie_manager, secret)
    st.stop()
    raise RuntimeError("unreachable")  # st.stop() 이 스크립트 실행을 여기서 끝낸다


def _ensure_gemini_key_cached(db, user_id: str) -> None:
    """엑셀 추출 시 주소 정제에 쓸 Gemini 키를 session_state 에 한 번만 읽어 둔다."""
    if GEMINI_API_KEY not in st.session_state and db is not None:
        st.session_state[GEMINI_API_KEY] = get_gemini_api_key(db, user_id)


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
    st.session_state.pop(GEMINI_API_KEY, None)  # 다음 계정이 이전 계정의 키를 물려받지 않도록
    # 쿠키 복원은 이미 시도한 것으로 표시해, 로그아웃 직후 다시 로그인되지 않게 한다.
    st.session_state[AUTH_COOKIE_CHECKED] = True
    # 실제 삭제는 로그인 폼과 함께 그려질 때 수행한다. 여기서 삭제 컴포넌트를 그려도
    # 호출부의 st.rerun() 이 iframe 을 곧바로 걷어내 삭제가 유실될 수 있다.
    st.session_state[AUTH_COOKIE_CLEAR_PENDING] = True


def _delete_auth_cookie(cookie_manager: stx.CookieManager) -> None:
    try:
        cookie_manager.delete(COOKIE_NAME, key="delete_auth_cookie")
    except KeyError:  # 컴포넌트가 아직 쿠키 목록을 받지 못한 경우
        pass


def require_staff(
    db, allow_admin_cookie: bool = False, require_nickname: bool = True
) -> tuple[str, str]:
    """URL 토큰으로 소유자를 확정하고, 닉네임 쿠키/입력을 받아 (owner_user_id, staff_name).

    ``allow_admin_cookie=True`` 면 관리자 로그인 쿠키만으로도 접근을 허용한다
    (검색 페이지 §4.5 전용. 주문 입력 페이지는 항상 토큰이 필요하다).

    ``require_nickname=False`` 면 토큰만 검증하고 닉네임 입력을 건너뛴다. 검색 페이지처럼
    접수자 닉네임을 실제로 쓰지 않는 화면에서 사용한다 (staff_name 은 "" 로 반환).
    """
    if allow_admin_cookie and LOGGED_IN_USER in st.session_state:
        admin_user = st.session_state[LOGGED_IN_USER]
        return admin_user, f"관리자({admin_user})"

    token = st.query_params.get("t")
    owner = get_owner_by_staff_token(db, token) if db is not None else None
    if not owner:
        st.error("유효하지 않거나 만료된 링크입니다. 관리자에게 새 링크를 요청하세요.")
        st.stop()
        raise RuntimeError("unreachable")

    if not require_nickname:
        return owner, ""

    if STAFF_NICKNAME not in st.session_state and not st.session_state.get(STAFF_COOKIE_CHECKED):
        st.session_state[STAFF_COOKIE_CHECKED] = True
        cookie_nickname = read_request_cookie(STAFF_NICKNAME_COOKIE)
        if cookie_nickname:
            st.session_state[STAFF_NICKNAME] = cookie_nickname

    if STAFF_NICKNAME in st.session_state:
        return owner, st.session_state[STAFF_NICKNAME]

    cookie_manager = stx.CookieManager(key=_STAFF_COOKIE_MANAGER_KEY)
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
