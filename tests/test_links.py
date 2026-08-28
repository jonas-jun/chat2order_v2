from core.links import origin_of, public_url

PATH = "/order?b=abc&t=xyz"


def test_origin_strips_path_and_query():
    assert origin_of("http://localhost:8501/order?b=abc&t=xyz") == "http://localhost:8501"
    assert origin_of("https://c2o-live.up.railway.app/search?t=xyz") == "https://c2o-live.up.railway.app"


def test_origin_of_blank_or_invalid_returns_empty():
    assert origin_of(None) == ""
    assert origin_of("") == ""
    assert origin_of("/order?b=abc") == ""  # scheme·host 없음


def test_public_url_prefers_configured_base():
    result = public_url(PATH, "https://live.example.com", "http://localhost:8501/")
    assert result == "https://live.example.com/order?b=abc&t=xyz"


def test_public_url_trims_trailing_slash_on_base():
    assert public_url(PATH, "https://live.example.com/", None) == "https://live.example.com/order?b=abc&t=xyz"


def test_public_url_falls_back_to_current_origin():
    result = public_url(PATH, "", "http://localhost:8501/")
    assert result == "http://localhost:8501/order?b=abc&t=xyz"


def test_public_url_none_base_uses_current_origin():
    result = public_url(PATH, None, "https://c2o-live.up.railway.app/")
    assert result == "https://c2o-live.up.railway.app/order?b=abc&t=xyz"


def test_public_url_relative_when_nothing_available():
    assert public_url(PATH, "", None) == PATH
    assert public_url(PATH, None, None) == PATH
