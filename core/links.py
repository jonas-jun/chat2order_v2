"""공유 링크(주문·검색) 의 절대 URL 조립.

관리자가 직원에게 복사해 주는 링크는 호스트가 포함된 full URL 이어야 한다.
우선순위: ``LIVE_PUBLIC_URL`` 설정값 → 현재 접속 주소의 origin → (둘 다 없으면)
상대경로.
"""

from __future__ import annotations

from urllib.parse import urlparse


def origin_of(url: str | None) -> str:
    """``http://host:port/path?q`` 에서 ``http://host:port`` 만 남긴다.

    scheme·host 를 모두 뽑지 못하면 빈 문자열을 반환한다.
    """
    if not url:
        return ""
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"


def public_url(path: str, configured_base: str | None, current_url: str | None) -> str:
    """공유용 절대 URL 을 만든다.

    ``configured_base`` (LIVE_PUBLIC_URL) 가 있으면 그것을, 없으면 ``current_url``
    의 origin 을 앞에 붙인다. 둘 다 없으면 ``path`` 를 그대로 돌려준다.
    """
    base = (configured_base or "").rstrip("/") or origin_of(current_url)
    return f"{base}{path}" if base else path
