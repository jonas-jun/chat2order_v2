"""부하 테스트: 방송 1개에 create_order N건을 동시에 저장해 주문번호 유일성과
지연을 측정한다 (Phase 6, §9 "동시 저장 시 주문번호 중복 0건" 검증용).

이 스크립트는 DB 계층(core.db.create_order)의 동시성만 검증한다. 실제 UI를
여러 브라우저로 동시에 쓰는 상황(위젯 rerun, 세션 초기화 등)은 검증하지
않으므로 별도로 사람이 하는 리허설이 필요하다.

사용:
    .venv/bin/python scripts/live_load_test.py                    # 기본 300건, worker 20
    .venv/bin/python scripts/live_load_test.py --orders 100 --workers 10
    .venv/bin/python scripts/live_load_test.py --keep              # 테스트 후 정리 안 함
    .venv/bin/python scripts/live_load_test.py --owner you@example.com

SUPABASE_URL / SUPABASE_KEY 를 .env 또는 환경변수로 읽는다. 테스트용 방송·
주문·상품은 정상 종료 시 자동으로 삭제한다(--keep 지정 시 남겨둔다).
"""

import argparse
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import db as dbfns  # noqa: E402
from core.models import Broadcast, CartItem, OrderDraft, Product, ProductInput  # noqa: E402
from core.settings import KST, get_env  # noqa: E402


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = min(len(ordered) - 1, int(len(ordered) * pct))
    return ordered[idx]


def _place_one_order(
    conn, broadcast: Broadcast, product: Product, seq: int
) -> tuple[float, str | None, Exception | None]:
    draft = OrderDraft(
        staff_name=f"load-{seq % 20}",
        customer_name=f"부하테스트{seq}",
        phone="01000000000",
        address="서울 강남구 테헤란로 1",
        items=[
            CartItem(
                product_id=product.id,
                product_name=product.product_name,
                option_name=product.option_name,
                unit_price=product.price,
                quantity=1,
            )
        ],
    )
    start = time.monotonic()
    try:
        order = dbfns.create_order(conn, broadcast, draft)
        return time.monotonic() - start, order.order_number, None
    except Exception as exc:  # noqa: BLE001 - 실패도 결과로 집계해야 한다
        return time.monotonic() - start, None, exc


def _cleanup(conn, broadcast_id: str) -> None:
    order_ids = [
        row["id"]
        for row in conn.table("live_orders").select("id").eq("broadcast_id", broadcast_id).execute().data
    ]
    if order_ids:
        conn.table("live_order_items").delete().in_("order_id", order_ids).execute()
        conn.table("live_orders").delete().in_("id", order_ids).execute()
    conn.table("live_products").delete().eq("broadcast_id", broadcast_id).execute()
    conn.table("live_broadcasts").delete().eq("id", broadcast_id).execute()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--orders", type=int, default=300)
    parser.add_argument("--workers", type=int, default=20)
    parser.add_argument("--owner", default=None, help="테스트 방송 소유자 user_id (기본: accounts 첫 계정)")
    parser.add_argument("--keep", action="store_true", help="테스트 후 생성된 방송/주문을 지우지 않는다")
    args = parser.parse_args()

    url, key = get_env("SUPABASE_URL"), get_env("SUPABASE_KEY")
    if not (url and key):
        print("SUPABASE_URL / SUPABASE_KEY 가 필요합니다.")
        return 1

    from supabase import create_client

    conn = create_client(url, key)

    owner = args.owner
    if not owner:
        accounts = conn.table("accounts").select("user_id").limit(1).execute().data
        if not accounts:
            print("accounts 테이블에 계정이 없습니다. --owner 로 지정하세요.")
            return 1
        owner = accounts[0]["user_id"]

    print(f"owner = {owner}, orders = {args.orders}, workers = {args.workers}")

    broadcast_id = dbfns.create_broadcast(
        conn,
        owner,
        "[LOAD TEST] 삭제 예정",
        datetime.now(KST),
        "live_load_test.py 자동 생성 — 정상 종료 시 자동 삭제됨",
        [ProductInput(product_name="부하테스트상품", option_name="단일상품", price=1000)],
    )
    broadcast = dbfns.get_broadcast(conn, broadcast_id)
    product = dbfns.list_products(conn, broadcast_id)[0]
    print(f"broadcast_id = {broadcast_id}")

    print(f"\n{args.orders}건 동시 저장 중 (worker {args.workers})...")
    latencies: list[float] = []
    order_numbers: list[str] = []
    errors: list[Exception] = []

    overall_start = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(_place_one_order, conn, broadcast, product, i) for i in range(args.orders)]
        for future in as_completed(futures):
            elapsed, order_number, exc = future.result()
            latencies.append(elapsed)
            if exc:
                errors.append(exc)
            else:
                order_numbers.append(order_number)
    overall_elapsed = time.monotonic() - overall_start

    print("\n결과")
    print(f"  성공: {len(order_numbers)} / {args.orders}")
    print(f"  실패: {len(errors)}")
    for exc in errors[:5]:
        print(f"    - {type(exc).__name__}: {exc}")

    duplicates = len(order_numbers) - len(set(order_numbers))
    print(f"  주문번호 중복: {duplicates}건")

    seqs = sorted(int(n[-3:]) for n in order_numbers)
    skipped = sum(b - a - 1 for a, b in zip(seqs, seqs[1:]) if b - a > 1)
    print(f"  순번 건너뜀: {skipped}건 (유일성만 보장되면 허용됨, 참고용)")

    ms = [v * 1000 for v in latencies]
    if ms:
        print(
            f"\n지연 시간(ms) — p50={_percentile(ms, 0.50):.0f} "
            f"p95={_percentile(ms, 0.95):.0f} p99={_percentile(ms, 0.99):.0f} max={max(ms):.0f}"
        )
    print(f"총 소요 시간: {overall_elapsed:.1f}s ({args.orders / overall_elapsed:.1f}건/초)")

    if args.keep:
        print(f"\n--keep 지정됨: 방송 {broadcast_id} 을(를) 남겨둡니다.")
    else:
        print("\n정리 중...")
        _cleanup(conn, broadcast_id)
        print("정리 완료.")

    return 1 if (duplicates or errors) else 0


if __name__ == "__main__":
    raise SystemExit(main())
