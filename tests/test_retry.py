import pytest

from core.retry import call_with_retry


def test_succeeds_on_first_try_without_delay():
    calls = []

    def fn():
        calls.append(1)
        return "ok"

    assert call_with_retry(fn, attempts=3, delay_seconds=0) == "ok"
    assert len(calls) == 1


def test_retries_then_succeeds():
    calls = []

    def fn():
        calls.append(1)
        if len(calls) < 3:
            raise ConnectionError("transient")
        return "ok"

    assert call_with_retry(fn, attempts=3, delay_seconds=0) == "ok"
    assert len(calls) == 3


def test_raises_last_exception_after_exhausting_attempts():
    calls = []

    def fn():
        calls.append(1)
        raise ConnectionError(f"boom {len(calls)}")

    with pytest.raises(ConnectionError, match="boom 3"):
        call_with_retry(fn, attempts=3, delay_seconds=0)
    assert len(calls) == 3


def test_does_not_swallow_non_exception_return_values():
    assert call_with_retry(lambda: None, attempts=2, delay_seconds=0) is None
