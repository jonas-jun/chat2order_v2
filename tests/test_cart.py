from core.cart import add_item, remove, set_quantity, total
from core.models import CartItem


def _item(**overrides):
    base = dict(product_id="p1", product_name="가디건", option_name="그레이", unit_price=1000, quantity=1)
    base.update(overrides)
    return CartItem(**base)


def test_add_item_appends_new_line():
    cart = add_item([], _item())
    assert len(cart) == 1
    assert cart[0].quantity == 1


def test_add_item_merges_same_product_and_option():
    cart = add_item([_item(quantity=1)], _item(quantity=2))
    assert len(cart) == 1
    assert cart[0].quantity == 3


def test_add_item_keeps_different_options_separate():
    cart = add_item([_item(option_name="그레이")], _item(option_name="블랙"))
    assert len(cart) == 2


def test_set_quantity_updates_given_index():
    cart = [_item(quantity=1), _item(product_id="p2", product_name="스커트", option_name="단일")]
    updated = set_quantity(cart, 0, 5)
    assert updated[0].quantity == 5
    assert updated[1].quantity == cart[1].quantity


def test_set_quantity_zero_or_less_removes_row():
    cart = [_item(), _item(product_id="p2", product_name="스커트", option_name="단일")]
    updated = set_quantity(cart, 0, 0)
    assert len(updated) == 1
    assert updated[0].product_id == "p2"


def test_remove_deletes_row_by_index():
    cart = [_item(), _item(product_id="p2", product_name="스커트", option_name="단일")]
    updated = remove(cart, 1)
    assert len(updated) == 1
    assert updated[0].product_id == "p1"


def test_total_sums_unit_price_times_quantity():
    cart = [_item(unit_price=1000, quantity=2), _item(product_id="p2", unit_price=3000, quantity=1)]
    assert total(cart) == 5000


def test_total_of_empty_cart_is_zero():
    assert total([]) == 0


def test_cart_functions_do_not_mutate_input():
    original = [_item(quantity=1)]
    add_item(original, _item(quantity=1))
    assert original[0].quantity == 1
