"""테스트/운영 계정에 직원 접속 토큰(accounts.staff_token)을 발급한다.

사용:
    .venv/bin/python scripts/set_staff_token.py you@example.com
    .venv/bin/python scripts/set_staff_token.py you@example.com --show   # 기존 토큰만 출력
    .venv/bin/python scripts/set_staff_token.py you@example.com --force  # 기존 값 덮어쓰기

SUPABASE_URL / SUPABASE_KEY(서비스 롤 키) 를 .env 에서 읽는다.
"""

import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.settings import get_env  # noqa: E402


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if not args:
        print(__doc__)
        return 1
    user_id = args[0]

    url, key = get_env("SUPABASE_URL"), get_env("SUPABASE_KEY")
    if not (url and key):
        print("SUPABASE_URL / SUPABASE_KEY 가 필요합니다.")
        return 1

    from supabase import create_client

    conn = create_client(url, key)

    rows = (
        conn.table("accounts")
        .select("user_id, staff_token, is_active")
        .eq("user_id", user_id)
        .execute()
        .data
    )
    if not rows:
        print(f"계정을 찾을 수 없습니다: {user_id}")
        return 1
    account = rows[0]
    existing = account.get("staff_token")

    if "--show" in flags:
        print(f"staff_token: {existing or '(없음)'}")
        return 0

    if existing and "--force" not in flags:
        print(f"이미 토큰이 있습니다. 재발급하려면 --force. 현재 값:\n  {existing}")
        return 0

    token = secrets.token_urlsafe(32)
    conn.table("accounts").update({"staff_token": token}).eq("user_id", user_id).execute()
    print("staff_token 발급 완료:")
    print(f"  {token}")
    base = get_env("LIVE_PUBLIC_URL", "").rstrip("/") or "(LIVE_PUBLIC_URL)"
    print("\n링크 예시:")
    print(f"  주문:  {base}/order?b=<broadcast_id>&t={token}")
    print(f"  검색:  {base}/search?t={token}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
