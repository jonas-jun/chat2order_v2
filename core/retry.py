"""일시적 네트워크 오류에 대한 재시도 유틸리티.

supabase-py 클라이언트 하나를 여러 세션이 공유하는 배포 형태(§5.3 `get_db()`
가 `st.cache_resource`)에서는 동시 저장이 몰릴 때 낮은 확률로 소켓 레벨
일시 오류(예: httpx ``ReadError``)가 난다. Phase 6 부하 테스트에서 확인:
20동시 요청 51% 실패 → 5동시 4% 실패로, 동시성이 낮아지면 대부분 해결되는
클라이언트 쪽 커넥션 경합이지 DB 로직 문제가 아니다. 즉시 재시도로 대부분
성공하므로, 사용자에게 실패를 보여주기 전에 몇 번 다시 시도한다.
"""

import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")


def call_with_retry(fn: Callable[[], T], attempts: int = 3, delay_seconds: float = 0.4) -> T:
    """``fn()`` 을 실행하고, 예외가 나면 짧게 대기 후 재시도한다.

    마지막 시도까지 실패하면 마지막 예외를 그대로 올린다.
    """
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - 마지막 시도까지 재시도 후 올린다
            last_exc = exc
            if attempt < attempts - 1:
                time.sleep(delay_seconds * (attempt + 1))
    assert last_exc is not None
    raise last_exc
