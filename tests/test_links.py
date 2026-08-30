from core.links import normalize_base, origin_of, public_url

PATH = "/order?b=abc&t=xyz"


def test_origin_strips_path_and_query():
    assert origin_of("http://localhost:8501/order?b=abc&t=xyz") == "http://localhost:8501"
    assert origin_of("https://c2o-live.up.railway.app/search?t=xyz") == "https://c2o-live.up.railway.app"


def test_origin_of_blank_or_invalid_returns_empty():
    assert origin_of(None) == ""
    assert origin_of("") == ""
    assert origin_of("/order?b=abc") == ""  # scheme·host 없음


def test_normalize_base_adds_https_to_bare_host():
    # RAILWAY_PUBLIC_DOMAIN 은 스킴 없이 호스트만 온다.
    assert normalize_base("c2o-live.up.railway.app") == "https://c2o-live.up.railway.app"


def test_normalize_base_keeps_scheme_and_drops_path():
    assert normalize_base("http://localhost:8501") == "http://localhost:8501"
    assert normalize_base("https://live.example.com/") == "https://live.example.com"
    assert normalize_base(" https://live.example.com/order?b=1 ") == "https://live.example.com"


def test_normalize_base_blank():
    assert normalize_base(None) == ""
    assert normalize_base("") == ""
    assert normalize_base("   ") == ""


def test_public_url_prefers_configured_base():
    result = public_url(PATH, "https://live.example.com", "http://localhost:8501/")
    assert result == "https://live.example.com/order?b=abc&t=xyz"


def test_public_url_trims_trailing_slash_on_base():
    assert public_url(PATH, "https://live.example.com/", None) == "https://live.example.com/order?b=abc&t=xyz"


def test_public_url_configured_base_without_scheme_still_absolute():
    assert public_url(PATH, "live.example.com", None) == "https://live.example.com/order?b=abc&t=xyz"


def test_public_url_falls_back_to_current_origin():
    result = public_url(PATH, "", "http://localhost:8501/")
    assert result == "http://localhost:8501/order?b=abc&t=xyz"


def test_public_url_none_base_uses_current_origin():
    result = public_url(PATH, None, "https://c2o-live.up.railway.app/")
    assert result == "https://c2o-live.up.railway.app/order?b=abc&t=xyz"


def test_public_url_uses_railway_domain_when_no_configured_base():
    # 운영에서 LIVE_PUBLIC_URL 을 비워 두면 Railway 주입 도메인이 쓰인다.
    result = public_url(PATH, "", None, "c2o-live.up.railway.app")
    assert result == "https://c2o-live.up.railway.app/order?b=abc&t=xyz"


def test_public_url_railway_domain_outranks_current_origin():
    # 프록시 뒤라 st.context.url 이 내부 주소일 수 있으므로 주입 도메인이 우선.
    result = public_url(PATH, None, "http://0.0.0.0:8080/", "c2o-live.up.railway.app")
    assert result == "https://c2o-live.up.railway.app/order?b=abc&t=xyz"


def test_public_url_configured_base_outranks_railway_domain():
    # 커스텀 도메인을 쓰는 경우를 위해 override 는 유지한다.
    result = public_url(PATH, "https://live.example.com", None, "c2o-live.up.railway.app")
    assert result == "https://live.example.com/order?b=abc&t=xyz"


def test_public_url_relative_when_nothing_available():
    assert public_url(PATH, "", None) == PATH
    assert public_url(PATH, None, None) == PATH
    assert public_url(PATH, "", None, "") == PATH
