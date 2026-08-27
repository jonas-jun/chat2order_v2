"""JUSO 우편번호 조회. 일괄 채움(Gemini 정제 포함)은 core/llm.py + Phase 4 참고."""

import logging

import requests

from core.models import AddressCandidate
from core.textutil import normalize_zip_code

logger = logging.getLogger(__name__)

_JUSO_URL = "https://business.juso.go.kr/addrlink/addrLinkApi.do"


def lookup_zip_code(address: str | None, juso_api_key: str) -> str | None:
    """도로명주소 검색API로 우편번호를 조회합니다."""
    if not address or not juso_api_key:
        return None
    try:
        resp = requests.get(
            _JUSO_URL,
            params={
                "confmKey": juso_api_key,
                "currentPage": 1,
                "countPerPage": 1,
                "keyword": address,
                "resultType": "json",
            },
            timeout=5,
        )
        juso_list = resp.json().get("results", {}).get("juso", [])
        if juso_list:
            return juso_list[0].get("zipNo")
    except Exception:
        logger.warning("우편번호 조회 실패", exc_info=True)
    return None


def search_addresses(keyword: str, juso_api_key: str, count: int = 5) -> list[AddressCandidate]:
    """주소 후보를 최대 ``count`` 건 조회한다.

    실패(네트워크 오류, API 오류)해도 예외를 올리지 않고 빈 리스트를 반환한다.
    로그에는 주소를 남기지 않는다(개인정보 보호, §9).
    """
    if not keyword or not juso_api_key:
        return []
    try:
        resp = requests.get(
            _JUSO_URL,
            params={
                "confmKey": juso_api_key,
                "currentPage": 1,
                "countPerPage": count,
                "keyword": keyword,
                "resultType": "json",
            },
            timeout=5,
        )
        data = resp.json()
        common = data.get("results", {}).get("common", {})
        error_code = common.get("errorCode")
        if error_code not in (None, "0"):
            logger.warning("JUSO 주소 검색 오류 errorCode=%s", error_code)
            return []
        juso_list = data.get("results", {}).get("juso", []) or []
    except Exception:
        logger.warning("주소 후보 조회 실패", exc_info=True)
        return []

    return [
        AddressCandidate(
            road_addr=item["roadAddr"],
            jibun_addr=item.get("jibunAddr"),
            zip_code=normalize_zip_code(item.get("zipNo")) or None,
        )
        for item in juso_list
        if item.get("roadAddr")
    ]
