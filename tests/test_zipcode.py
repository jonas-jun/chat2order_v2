import pytest

from core import zipcode


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
