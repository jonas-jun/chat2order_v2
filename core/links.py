"""공유 링크(주문·검색) 의 절대 URL 조립.

관리자가 직원에게 복사해 주는 링크는 호스트가 포함된 full URL 이어야 한다.
우선순위: ``LIVE_PUBLIC_URL`` 설정값 → Railway 가 주입하는 ``RAILWAY_PUBLIC_DOMAIN``
→ 현재 접속 주소의 origin → (모두 없으면) 상대경로.

``LIVE_PUBLIC_URL`` 은 커스텀 도메인을 쓸 때만 필요한 override 다. 운영 도메인을
손으로 복제해 두면 서비스 이름·도메인이 바뀔 때 조용히 어긋나므로(#16), 비워 두고
``RAILWAY_PUBLIC_DOMAIN`` 에 맡기는 쪽을 기본으로 삼는다.
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


def normalize_base(value: str | None) -> str:
    """설정값을 ``scheme://host`` 형태의 base 로 다듬는다.

    ``RAILWAY_PUBLIC_DOMAIN`` 처럼 스킴 없이 호스트만 오는 값과, 실수로 스킴을
    빠뜨린 ``LIVE_PUBLIC_URL`` 을 모두 받아 준다. 경로·쿼리는 버린다.
    """
    value = (value or "").strip().rstrip("/")
    if not value:
        return ""
    if "//" not in value:
        value = f"https://{value}"
    return origin_of(value)


def public_url(
    path: str,
    configured_base: str | None,
    current_url: str | None,
    railway_domain: str | None = None,
) -> str:
    """공유용 절대 URL 을 만든다.

    ``configured_base`` (LIVE_PUBLIC_URL) → ``railway_domain``
    (RAILWAY_PUBLIC_DOMAIN) → ``current_url`` 의 origin 순으로 앞에 붙인다.
    모두 없으면 ``path`` 를 그대로 돌려준다.
    """
    base = (
        normalize_base(configured_base)
        or normalize_base(railway_domain)
        or origin_of(current_url)
    )
    return f"{base}{path}" if base else path
