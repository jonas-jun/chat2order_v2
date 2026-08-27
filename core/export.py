"""엑셀 변환. config.yaml 의 ``live_output*`` 설정을 받아 DataFrame/엑셀 바이트를 만든다."""

import pandas as pd

from core.excel import write_excel_with_text_zipcode
from core.models import OrderRow


def _item_summary(order: OrderRow) -> str:
    return "; ".join(f"{i.product_name} {i.option_name} x{i.quantity}" for i in order.items)


def _flatten(order: OrderRow, row_mode: str) -> list[dict]:
    base = {
        "order_number": order.order_number,
        "chat_name": order.chat_name,
        "customer_name": order.customer_name,
        "phone": order.phone,
        "full_address": order.full_address,
        "zip_code": order.zip_code,
        "staff_name": order.staff_name,
        "created_at_kst": order.created_at_kst,
    }

    if row_mode == "order":
        return [
            {
                **base,
                "product_name": _item_summary(order),
                "option_name": None,
                "quantity": sum(item.quantity for item in order.items),
                "unit_price": None,
            }
        ]

    if not order.items:
        return [{**base, "product_name": None, "option_name": None, "quantity": None, "unit_price": None}]

    return [
        {
            **base,
            "product_name": item.product_name,
            "option_name": item.option_name,
            "quantity": item.quantity,
            "unit_price": item.unit_price,
        }
        for item in order.items
    ]


def rows_to_frame(
    orders: list[OrderRow], columns_map: dict[str, str | None], row_mode: str = "item"
) -> pd.DataFrame:
    """OrderRow 리스트를 ``{출력 컬럼명: 원본 필드명}`` 매핑에 따라 DataFrame 으로 변환한다.

    ``row_mode="item"`` 이면 상품 1행(아이템 수만큼 행 복제), ``row_mode="order"``
    면 주문 1행(아이템은 ``"상품 옵션 ×수량; …"`` 한 셀로 결합)으로 만든다.
    """
    flat_rows: list[dict] = []
    for order in orders:
        flat_rows.extend(_flatten(order, row_mode))

    data = {
        output_name: [row.get(field) if field else None for row in flat_rows]
        for output_name, field in columns_map.items()
    }
    return pd.DataFrame(data, columns=list(columns_map.keys()))


def build_excel(
    frame: pd.DataFrame,
    review_frame: pd.DataFrame | None,
    sheet_name: str,
    review_sheet_name: str,
    zip_col: str = "우편번호",
) -> bytes:
    extra_sheets = (
        {review_sheet_name: review_frame}
        if review_frame is not None and not review_frame.empty
        else None
    )
    return write_excel_with_text_zipcode(frame, sheet_name, zip_col=zip_col, extra_sheets=extra_sheets)
