"""Supabase(PostgreSQL)에 sql/live_schema.sql 을 적용한다.

Supabase SQL Editor 에 붙여넣는 것과 동일한 결과. DDL 은 모두 멱등
(`if not exists`, `create or replace`)이라 여러 번 실행해도 안전하다.

사용:
    .venv/bin/python scripts/apply_schema.py           # 실행
    .venv/bin/python scripts/apply_schema.py --dry-run # SQL 만 출력

DATABASE_URL 은 .env 또는 환경변수로 준다. (Supabase 대시보드 >
Project Settings > Database > Connection string > URI)
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.settings import get_env  # noqa: E402

SCHEMA_PATH = ROOT / "sql" / "live_schema.sql"


def main() -> int:
    sql = SCHEMA_PATH.read_text(encoding="utf-8")

    if "--dry-run" in sys.argv:
        print(sql)
        return 0

    dsn = get_env("DATABASE_URL")
    if not dsn:
        print("DATABASE_URL 이 없습니다. .env 에 Supabase Postgres 연결 문자열을 넣으세요.")
        return 1

    try:
        import psycopg
    except ModuleNotFoundError:
        print("psycopg 미설치: .venv/bin/pip install 'psycopg[binary]'")
        return 1

    print(f"연결 중... ({dsn.split('@')[-1]})")
    with psycopg.connect(dsn, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        # 적용 결과 확인
        with conn.cursor() as cur:
            cur.execute(
                "select table_name from information_schema.tables "
                "where table_schema = 'public' and table_name like 'live\\_%' "
                "order by table_name"
            )
            tables = [r[0] for r in cur.fetchall()]
            cur.execute(
                "select column_name from information_schema.columns "
                "where table_name = 'accounts' and column_name = 'staff_token'"
            )
            has_token = cur.fetchone() is not None

    print("적용 완료.")
    print(f"  live_* 테이블: {', '.join(tables) or '(없음)'}")
    print(f"  accounts.staff_token 컬럼: {'있음' if has_token else '없음'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
