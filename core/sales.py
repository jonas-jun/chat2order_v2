"""상품별 주문 수량 집계의 순수 함수. ``core/cart.py`` 와 같은 패턴 — 로직은
여기 두고 페이지는 얇게 유지한다.

DB 가 돌려주는 집계(:func:`core.db.aggregate_product_sales`)는 "주문이 1건이라도
있는" (상품, 옵션) 만 담고 있다. 화면에는 아직 안 나간 옵션도 0 으로 보여야
"그 옵션은 아직 하나도 안 나갔어요" 라고 답할 수 있으므로, 방송 카탈로그를
기준으로 좌측 결합해 빈 자리를 채우는 것이 이 모듈의 핵심이다.
"""

from __future__ import annotations

from core.models import OrderDraft, Product, ProductSalesGroup, ProductSalesRow

_SalesKey = tuple[str, str]


def merge_with_catalog(
    products: list[Product], sales: list[ProductSalesRow]
) -> list[ProductSalesRow]:
    """카탈로그 순서(``sort_order``)로 집계를 펼치고, 안 팔린 옵션은 0 으로 채운다.

    카탈로그에 없는 집계 행(상품 교체 등으로 스냅샷에만 남은 항목)은 누락시키지
    않고 뒤에 이름순으로 덧붙인다.
    """
    by_key: dict[_SalesKey, ProductSalesRow] = {
        (row.product_name, row.option_name): row for row in sales
    }

    merged: list[ProductSalesRow] = []
    for product in products:
        key = (product.product_name, product.option_name)
        sold = by_key.pop(key, None)
        if sold is None:
            sold = ProductSalesRow(product_name=key[0], option_name=key[1])
        merged.append(sold)

    orphans = sorted(by_key.values(), key=lambda row: (row.product_name, row.option_name))
    return merged + orphans


def product_names(rows: list[ProductSalesRow]) -> list[str]:
    """드롭다운에 채울 상품명. 카탈로그 순서를 유지하고 중복을 없앤다."""
    return list(dict.fromkeys(row.product_name for row in rows))


def group_for(rows: list[ProductSalesRow], product_name: str) -> ProductSalesGroup | None:
    """상품 하나의 옵션 집계 묶음. 그 이름의 행이 없으면 ``None``."""
    option_rows = [row for row in rows if row.product_name == product_name]
    if not option_rows:
        return None
    return ProductSalesGroup(product_name=product_name, rows=option_rows)


def pending_quantities(pending: list[OrderDraft]) -> dict[_SalesKey, int]:
    """아직 제출하지 않은 주문의 (상품, 옵션)별 수량.

    미제출 큐는 세션 안에만 있어 다른 직원에게는 보이지 않는다. 그래서 DB 집계에
    합치지 않고 "내 미제출" 로 따로 보여준다 — 합치면 같은 방송을 보는 직원마다
    총합이 달라진다.
    """
    quantities: dict[_SalesKey, int] = {}
    for draft in pending:
        for item in draft.items:
            key = (item.product_name, item.option_name)
            quantities[key] = quantities.get(key, 0) + item.quantity
    return quantities
