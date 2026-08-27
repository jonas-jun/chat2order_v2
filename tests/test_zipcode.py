from datetime import datetime

import pytest

from core import zipcode
from core.models import OrderRow
from core.settings import KST


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


def _juso_payload(items, error_code="0"):
    return {"results": {"common": {"errorCode": error_code}, "juso": items}}


def test_search_addresses_returns_candidates(monkeypatch):
    payload = _juso_payload(
        [
            {"roadAddr": "서울 강남구 테헤란로 1", "jibunAddr": "역삼동 1", "zipNo": "6134"},
            {"roadAddr": "서울 강남구 테헤란로 2", "jibunAddr": "역삼동 2", "zipNo": "06135"},
        ]
    )
    monkeypatch.setattr(zipcode.requests, "get", lambda *a, **kw: _FakeResponse(payload))

    candidates = zipcode.search_addresses("테헤란로", "fake-key")

    assert len(candidates) == 2
    assert candidates[0].road_addr == "서울 강남구 테헤란로 1"
    assert candidates[0].zip_code == "06134"


def test_search_addresses_returns_empty_on_error_code(monkeypatch):
    payload = _juso_payload([], error_code="E0001")
    monkeypatch.setattr(zipcode.requests, "get", lambda *a, **kw: _FakeResponse(payload))

    assert zipcode.search_addresses("이상한주소", "fake-key") == []


def test_search_addresses_returns_empty_on_exception(monkeypatch):
    def _raise(*a, **kw):
        raise ConnectionError("network down")

    monkeypatch.setattr(zipcode.requests, "get", _raise)

    assert zipcode.search_addresses("테헤란로", "fake-key") == []


def test_search_addresses_requires_keyword_and_key():
    assert zipcode.search_addresses("", "fake-key") == []
    assert zipcode.search_addresses("테헤란로", "") == []


def test_search_addresses_skips_items_without_road_addr(monkeypatch):
    payload = _juso_payload([{"jibunAddr": "역삼동 1", "zipNo": "06134"}])
    monkeypatch.setattr(zipcode.requests, "get", lambda *a, **kw: _FakeResponse(payload))

    assert zipcode.search_addresses("테헤란로", "fake-key") == []


def test_lookup_zip_code_returns_first_hit(monkeypatch):
    payload = _juso_payload([{"roadAddr": "서울 강남구 테헤란로 1", "zipNo": "06134"}])
    monkeypatch.setattr(zipcode.requests, "get", lambda *a, **kw: _FakeResponse(payload))

    assert zipcode.lookup_zip_code("서울 강남구 테헤란로 1", "fake-key") == "06134"


def test_lookup_zip_code_returns_none_without_address_or_key():
    assert zipcode.lookup_zip_code(None, "fake-key") is None
    assert zipcode.lookup_zip_code("주소", "") is None


@pytest.mark.parametrize("exc", [ConnectionError, TimeoutError])
def test_lookup_zip_code_swallows_request_exceptions(monkeypatch, exc):
    def _raise(*a, **kw):
        raise exc("boom")

    monkeypatch.setattr(zipcode.requests, "get", _raise)
    assert zipcode.lookup_zip_code("서울 강남구 테헤란로 1", "fake-key") is None


def _order(order_id: str, address: str, search_address: str | None = None, zip_code: str | None = None) -> OrderRow:
    return OrderRow(
        id=order_id,
        broadcast_id="b1",
        order_number="20260830001",
        staff_name="민지",
        customer_name="홍길동",
        phone="010-1234-5678",
        address=address,
        full_address=address,
        zip_code=zip_code,
        search_address=search_address,
        created_at=datetime(2026, 8, 30, 20, 0, tzinfo=KST),
        created_at_kst="2026-08-30 20:00:00",
        items=[],
    )


def test_fill_zip_codes_direct_hit(monkeypatch):
    monkeypatch.setattr(zipcode, "lookup_zip_code", lambda addr, key: "06134")
    orders = [_order("o1", "서울 강남구 테헤란로 1")]

    results = zipcode.fill_zip_codes(orders, juso_api_key="key")

    assert results["o1"].stage == "direct"
    assert results["o1"].zip_code == "06134"
    assert results["o1"].search_address is None


def test_fill_zip_codes_refines_with_gemini_on_direct_failure(monkeypatch):
    calls = []

    def fake_lookup(addr, key):
        calls.append(addr)
        return "06134" if addr == "정제된 주소" else None

    monkeypatch.setattr(zipcode, "lookup_zip_code", fake_lookup)
    monkeypatch.setattr(
        zipcode, "extract_search_address", lambda *a, **kw: "정제된 주소"
    )
    orders = [_order("o1", "서울 강남구 상세동 101호")]

    results = zipcode.fill_zip_codes(
        orders, juso_api_key="key", gemini_api_key="gkey", prompt_template="{address}"
    )

    assert results["o1"].stage == "refined"
    assert results["o1"].zip_code == "06134"
    assert results["o1"].search_address == "정제된 주소"
    assert calls == ["서울 강남구 상세동 101호", "정제된 주소"]


def test_fill_zip_codes_both_fail_still_stores_refined_address(monkeypatch):
    monkeypatch.setattr(zipcode, "lookup_zip_code", lambda addr, key: None)
    monkeypatch.setattr(zipcode, "extract_search_address", lambda *a, **kw: "정제된 주소")
    orders = [_order("o1", "이상한 주소")]

    results = zipcode.fill_zip_codes(
        orders, juso_api_key="key", gemini_api_key="gkey", prompt_template="{address}"
    )

    assert results["o1"].stage == "failed"
    assert results["o1"].zip_code is None
    assert results["o1"].search_address == "정제된 주소"


def test_fill_zip_codes_reuses_stored_search_address_without_calling_gemini(monkeypatch):
    def fail_if_called(*a, **kw):
        raise AssertionError("Gemini should not be called when search_address already stored")

    monkeypatch.setattr(zipcode, "lookup_zip_code", lambda addr, key: "06134" if addr == "이미 정제된 주소" else None)
    monkeypatch.setattr(zipcode, "extract_search_address", fail_if_called)
    orders = [_order("o1", "원본 주소", search_address="이미 정제된 주소")]

    results = zipcode.fill_zip_codes(
        orders, juso_api_key="key", gemini_api_key="gkey", prompt_template="{address}"
    )

    assert results["o1"].stage == "refined"
    assert results["o1"].zip_code == "06134"
    assert results["o1"].search_address == "이미 정제된 주소"


def test_fill_zip_codes_dedupes_same_address_across_orders(monkeypatch):
    call_count = {"n": 0}

    def fake_lookup(addr, key):
        call_count["n"] += 1
        return "06134"

    monkeypatch.setattr(zipcode, "lookup_zip_code", fake_lookup)
    orders = [_order("o1", "서울 강남구 테헤란로 1"), _order("o2", "서울 강남구 테헤란로 1")]

    results = zipcode.fill_zip_codes(orders, juso_api_key="key")

    assert call_count["n"] == 1
    assert results["o1"].zip_code == results["o2"].zip_code == "06134"


def test_fill_zip_codes_reports_progress(monkeypatch):
    monkeypatch.setattr(zipcode, "lookup_zip_code", lambda addr, key: "06134")
    orders = [_order("o1", "주소1"), _order("o2", "주소2")]
    progress_calls = []

    zipcode.fill_zip_codes(orders, juso_api_key="key", progress_cb=lambda done, total: progress_calls.append((done, total)))

    assert progress_calls == [(1, 2), (2, 2)]
