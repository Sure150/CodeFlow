def line_subtotal(unit_price: int, quantity: int) -> int:
    return unit_price * quantity


def discount_for(subtotal: int) -> int:
    return subtotal // 10 if subtotal >= 5_000 else 0


def line_total(unit_price: int, quantity: int) -> int:
    subtotal = line_subtotal(unit_price, quantity)
    return subtotal - discount_for(subtotal)
