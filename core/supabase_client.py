"""끊어진 커넥션에서 살아남는 supabase 클라이언트 생성.

``get_db()`` 는 ``st.cache_resource`` 라서 supabase 클라이언트 하나(=httpx 커넥션
풀 하나)를 프로세스 수명 내내 모든 세션이 공유한다. 그 풀의 연결은 우리가 모르는
사이에 서버 쪽에서 끊길 수 있다 — Supabase 엣지가 HTTP/2 GOAWAY 를 보내거나
keep-alive 연결을 회수하는 경우다. httpx 는 그 사실을 모른 채 죽은 연결로 요청을
보내고 ``httpx.RemoteProtocolError`` 를 올린다.

postgrest 의 자체 재시도(``send_with_retry``)는 503/520 **응답**만 다룬다. 응답이
아예 오지 않는 이런 전송 계층 예외는 그대로 위로 올라가, 로그인 직후 첫 조회
(``pages/admin.py`` 의 ``list_broadcasts``)에서 페이지 전체가 트레이스백으로
깨졌다.

그래서 전송 계층에서 한 번 다시 보낸다. 죽은 연결은 이미 풀에서 빠졌으므로
재시도는 새 연결로 나간다. **조회(GET/HEAD)만** 재시도한다 — 쓰기는 서버가 이미
처리한 뒤에 연결이 끊겼을 수 있고, 그때 다시 보내면 주문이 중복 접수된다.
쓰기 쪽 일시 오류는 호출부의 :func:`core.retry.call_with_retry` 가 맡는다.
"""

from __future__ import annotations

import httpx
from supabase import create_client
from supabase.lib.client_options import SyncClientOptions

# postgrest 기본값과 맞춘다 (postgrest.constants.DEFAULT_POSTGREST_CLIENT_TIMEOUT).
# 클라이언트를 직접 넘기면 postgrest 는 타임아웃을 설정해 주지 않으므로 여기서 준다.
REQUEST_TIMEOUT_SECONDS = 120

# 재시도해도 안전한 메서드. 조회는 몇 번을 보내도 결과가 같다.
_IDEMPOTENT_METHODS = frozenset({"GET", "HEAD"})

# "응답을 받기 전에 연결이 끊겼다" 를 뜻하는 예외들. 요청이 서버에 닿았는지는
# 알 수 없으므로 위 조건(조회 전용)과 함께 쓸 때만 재시도해도 안전하다.
_CONNECTION_LOST = (httpx.RemoteProtocolError, httpx.ReadError, httpx.WriteError)


class ReconnectingTransport(httpx.HTTPTransport):
    """끊어진 연결로 실패한 조회 요청을 새 연결로 한 번 더 보낸다."""

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        try:
            return super().handle_request(request)
        except _CONNECTION_LOST:
            if request.method not in _IDEMPOTENT_METHODS:
                raise
            return super().handle_request(request)


def build_httpx_client() -> httpx.Client:
    """supabase 가 쓸 httpx 클라이언트. 인자는 supabase 기본값을 그대로 따른다."""
    return httpx.Client(
        # http2/풀 설정은 transport 가 관리하므로 Client 가 아니라 transport 에 준다.
        transport=ReconnectingTransport(http2=True, retries=1),
        follow_redirects=True,
        timeout=httpx.Timeout(REQUEST_TIMEOUT_SECONDS),
    )


def create_supabase_client(url: str, key: str):
    """``supabase.create_client`` 와 같되, 재시도하는 transport 를 끼운다.

    클라이언트를 직접 넘겨도 postgrest 는 요청마다 절대 URL 과 인증 헤더를 따로
    실어 보내므로, base_url·헤더를 우리가 채워 줄 필요는 없다.
    """
    return create_client(url, key, options=SyncClientOptions(httpx_client=build_httpx_client()))
