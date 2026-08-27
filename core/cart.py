"""장바구니 순수 함수. 세션 상태(list[CartItem])를 직접 변형하지 않고 새 리스트를 반환한다."""

from core.models import CartItem


def _same_line(a: CartItem, b: CartItem) -> bool:
    return (a.product_id, a.product_name, a.option_name) == (
        b.product_id,
        b.product_name,
        b.option_name,
    )


def add_item(cart: list[CartItem], item: CartItem) -> list[CartItem]:
    """같은 (상품, 옵션) 이 이미 있으면 수량을 합산하고, 없으면 새로 추가한다."""
    updated: list[CartItem] = []
    merged = False
    for existing in cart:
        if _same_line(existing, item):
            updated.append(existing.model_copy(update={"quantity": existing.quantity + item.quantity}))
            merged = True
        else:
            updated.append(existing)
    if not merged:
        updated.append(item)
    return updated


def set_quantity(cart: list[CartItem], index: int, quantity: int) -> list[CartItem]:
    """수량을 0 이하로 바꾸면 해당 행을 삭제한다."""
    if quantity <= 0:
        return remove(cart, index)
    updated = list(cart)
    updated[index] = updated[index].model_copy(update={"quantity": quantity})
    return updated


def remove(cart: list[CartItem], index: int) -> list[CartItem]:
    updated = list(cart)
    del updated[index]
    return updated


def total(cart: list[CartItem]) -> int:
    return sum(item.unit_price * item.quantity for item in cart)
