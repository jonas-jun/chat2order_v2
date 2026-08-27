"""JUSO 우편번호 조회 + Gemini 정제를 포함한 일괄 채움(§4.4)."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import requests

from core.llm import extract_search_address
from core.models import AddressCandidate, OrderRow
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


@dataclass
class ZipFillResult:
    zip_code: str | None
    search_address: str | None
    stage: Literal["direct", "refined", "failed"]


def fill_zip_codes(
    orders: list[OrderRow],
    juso_api_key: str,
    gemini_api_key: str = "",
    model: str = "",
    temperature: float = 0.1,
    prompt_template: str = "",
    progress_cb: Callable[[int, int], None] | None = None,
) -> dict[str, ZipFillResult]:
    """주문 리스트의 우편번호를 일괄 채운다.

    같은 주소(``address`` 문자열 trim 기준)는 한 번만 조회하고 결과를 재사용한다.
    1차: JUSO 에 원문 주소 그대로 조회. 2차(1차 실패 시): 이미 저장된
    ``search_address`` 가 있으면 그것으로 JUSO 재조회(LLM 재호출 없음), 없으면
    Gemini 로 도로명주소를 정제한 뒤 JUSO 재조회.
    """
    use_gemini = bool(gemini_api_key and prompt_template)

    groups: dict[str, list[OrderRow]] = {}
    for order in orders:
        groups.setdefault((order.address or "").strip(), []).append(order)

    unique_addrs = list(groups.keys())
    total = len(unique_addrs)
    results: dict[str, ZipFillResult] = {}

    for i, raw_address in enumerate(unique_addrs):
        group = groups[raw_address]
        result = _resolve_one_address(
            raw_address, group, juso_api_key, gemini_api_key, model, temperature,
            prompt_template, use_gemini,
        )
        for order in group:
            results[order.id] = result
        if progress_cb:
            progress_cb(i + 1, total)

    return results


def _resolve_one_address(
    raw_address: str,
    group: list[OrderRow],
    juso_api_key: str,
    gemini_api_key: str,
    model: str,
    temperature: float,
    prompt_template: str,
    use_gemini: bool,
) -> ZipFillResult:
    if not raw_address:
        return ZipFillResult(zip_code=None, search_address=None, stage="failed")

    zip_code = lookup_zip_code(raw_address, juso_api_key)
    if zip_code:
        return ZipFillResult(zip_code=normalize_zip_code(zip_code) or None, search_address=None, stage="direct")

    existing_search_address = next((o.search_address for o in group if o.search_address), None)
    if existing_search_address:
        zip_code = lookup_zip_code(existing_search_address, juso_api_key)
        stage = "refined" if zip_code else "failed"
        return ZipFillResult(
            zip_code=normalize_zip_code(zip_code) or None,
            search_address=existing_search_address,
            stage=stage,
        )

    if use_gemini:
        refined = extract_search_address(gemini_api_key, raw_address, model, temperature, prompt_template)
        if refined:
            zip_code = lookup_zip_code(refined, juso_api_key)
            stage = "refined" if zip_code else "failed"
            return ZipFillResult(
                zip_code=normalize_zip_code(zip_code) or None, search_address=refined, stage=stage
            )

    return ZipFillResult(zip_code=None, search_address=None, stage="failed")
