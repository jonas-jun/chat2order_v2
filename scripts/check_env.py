"""외부 서비스 연결 점검: Supabase / JUSO / Gemini.

사용:  .venv/bin/python scripts/check_env.py

.env(또는 환경변수)의 값으로 각 서비스에 실제 요청을 한 번씩 보내 본다.
개인정보는 출력하지 않는다.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.settings import get_env  # noqa: E402

OK = "\033[32mOK\033[0m"
FAIL = "\033[31mFAIL\033[0m"
SKIP = "\033[33mSKIP\033[0m"


def _line(name: str, status: str, detail: str = "") -> None:
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def check_vars() -> bool:
    print("환경변수")
    required = ["SUPABASE_URL", "SUPABASE_KEY", "JUSO_API_KEY", "AUTH_SECRET"]
    optional = ["LIVE_PUBLIC_URL", "TZ", "DATABASE_URL", "GEMINI_API_KEY"]
    all_ok = True
    for name in required:
        val = get_env(name)
        _line(name, OK if val else FAIL, "" if val else "미설정 (필수)")
        all_ok = all_ok and bool(val)
    for name in optional:
        val = get_env(name)
        _line(name, OK if val else SKIP, "" if val else "미설정 (선택)")
    return all_ok


def check_supabase() -> bool:
    print("\nSupabase")
    url, key = get_env("SUPABASE_URL"), get_env("SUPABASE_KEY")
    if not (url and key):
        _line("connect", SKIP, "SUPABASE_URL/KEY 없음")
        return False
    try:
        from supabase import create_client

        conn = create_client(url, key)
        conn.table("accounts").select("user_id").limit(1).execute()
        _line("accounts 조회", OK)
        for t in ("live_broadcasts", "live_products", "live_orders", "live_order_items"):
            try:
                conn.table(t).select("id").limit(1).execute()
                _line(t, OK)
            except Exception as e:
                _line(t, FAIL, f"{type(e).__name__} (스키마 미적용?)")
                return False
        return True
    except Exception as e:
        _line("connect", FAIL, f"{type(e).__name__}: {e}")
        return False


def check_juso() -> bool:
    print("\nJUSO 도로명주소 API")
    key = get_env("JUSO_API_KEY")
    if not key:
        _line("lookup", SKIP, "JUSO_API_KEY 없음")
        return False
    from core.zipcode import search_addresses

    results = search_addresses("서울 중구 세종대로 110", key, count=3)
    if results:
        _line("검색", OK, f"{len(results)}건, 우편번호 예: {results[0].zip_code}")
        return True
    _line("검색", FAIL, "결과 없음 (키 승인 상태·IP 확인)")
    return False


def check_gemini() -> bool:
    print("\nGemini (주소 정제, 엑셀 추출 전용)")
    key = get_env("GEMINI_API_KEY")
    if not key:
        _line("generate", SKIP, "GEMINI_API_KEY 없음 — 운영은 accounts.gemini_api_key 사용")
        return True  # 선택 사항이므로 전체 실패로 치지 않는다
    from core.llm import extract_search_address

    prompt = (ROOT / "prompts" / "address_to_search.txt").read_text(encoding="utf-8")
    out = extract_search_address(
        api_key=key,
        address="부산 북구 백양대로1050번길 16 삼정그린코아 102동 1203호",
        model="gemini-3.1-flash-lite",
        temperature=0.1,
        prompt_template=prompt,
    )
    if out:
        _line("generate", OK, f"정제 결과: {out!r}")
        return True
    _line("generate", FAIL, "None 반환 (키·모델명 확인)")
    return False


def main() -> int:
    results = [
        check_vars(),
        check_supabase(),
        check_juso(),
        check_gemini(),
    ]
    print()
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
