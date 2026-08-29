import httpx
import pytest

from core.supabase_client import (
    REQUEST_TIMEOUT_SECONDS,
    ReconnectingTransport,
    build_httpx_client,
)


def make_transport(monkeypatch, outcomes):
    """``outcomes`` 를 차례로 내놓는 가짜 하위 전송으로 감싼 transport 를 만든다.

    항목이 예외면 raise 하고, 아니면 그대로 응답으로 돌려준다.
    """
    calls = []

    def fake_handle_request(self, request):
        calls.append(request)
        outcome = outcomes[len(calls) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", fake_handle_request)
    return ReconnectingTransport(), calls


def request(method="GET"):
    return httpx.Request(method, "https://example.supabase.co/rest/v1/live_broadcasts")


def ok():
    return httpx.Response(200, json=[])


def connection_terminated():
    # 로그인 직후 조회에서 실제로 올라온 예외 (Supabase 엣지의 HTTP/2 GOAWAY).
    return httpx.RemoteProtocolError("<ConnectionTerminated error_code:1, last_stream_id:15>")


def test_successful_read_is_sent_once(monkeypatch):
    transport, calls = make_transport(monkeypatch, [ok()])
    assert transport.handle_request(request()).status_code == 200
    assert len(calls) == 1


def test_read_retries_once_after_connection_is_terminated(monkeypatch):
    transport, calls = make_transport(monkeypatch, [connection_terminated(), ok()])
    assert transport.handle_request(request()).status_code == 200
    assert len(calls) == 2


@pytest.mark.parametrize(
    "error",
    [connection_terminated(), httpx.ReadError("socket closed"), httpx.WriteError("broken pipe")],
)
def test_all_connection_lost_errors_are_retried_for_reads(monkeypatch, error):
    transport, calls = make_transport(monkeypatch, [error, ok()])
    assert transport.handle_request(request()).status_code == 200
    assert len(calls) == 2


def test_read_gives_up_after_one_retry(monkeypatch):
    transport, calls = make_transport(
        monkeypatch, [connection_terminated(), connection_terminated()]
    )
    with pytest.raises(httpx.RemoteProtocolError):
        transport.handle_request(request())
    assert len(calls) == 2


@pytest.mark.parametrize("method", ["POST", "PATCH", "DELETE"])
def test_writes_are_never_retried(monkeypatch, method):
    """서버가 이미 주문을 저장한 뒤 연결이 끊겼을 수 있어 중복 접수를 만든다."""
    transport, calls = make_transport(monkeypatch, [connection_terminated(), ok()])
    with pytest.raises(httpx.RemoteProtocolError):
        transport.handle_request(request(method))
    assert len(calls) == 1


def test_unrelated_errors_are_not_retried(monkeypatch):
    transport, calls = make_transport(monkeypatch, [httpx.PoolTimeout("pool exhausted"), ok()])
    with pytest.raises(httpx.PoolTimeout):
        transport.handle_request(request())
    assert len(calls) == 1


def test_built_client_uses_reconnecting_transport_with_a_timeout():
    client = build_httpx_client()
    assert isinstance(client._transport, ReconnectingTransport)
    assert client.timeout.read == REQUEST_TIMEOUT_SECONDS
    client.close()
