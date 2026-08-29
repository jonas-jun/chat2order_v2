"""미제출 주문 큐 순수 함수. 세션 상태(list[OrderDraft])를 직접 변형하지 않고 새 리스트를 반환한다.

직원이 "주문 담기" 로 쌓아둔 주문을 "전체 제출" 전까지 세션에만 보관한다.
``core/cart.py`` 와 같은 패턴 — 로직은 여기 두고 페이지는 얇게 유지한다.
"""

from core.models import OrderDraft


def append(pending: list[OrderDraft], draft: OrderDraft) -> list[OrderDraft]:
    """큐 맨 뒤에 주문을 추가한다 (병합하지 않는다 — 서로 다른 고객 주문이므로)."""
    return [*pending, draft]


def remove(pending: list[OrderDraft], index: int) -> list[OrderDraft]:
    updated = list(pending)
    del updated[index]
    return updated


def total_amount(pending: list[OrderDraft]) -> int:
    """큐 전체 금액 합계."""
    return sum(
        item.unit_price * item.quantity for draft in pending for item in draft.items
    )


def duplicate_phone_count(pending: list[OrderDraft], phone_digits: str) -> int:
    """큐 안에서 같은 전화번호(숫자만)를 가진 주문 수. 빈 값이면 0."""
    if not phone_digits:
        return 0
    return sum(1 for draft in pending if draft.phone_digits == phone_digits)
