from dataclasses import dataclass

from helpers import normalize as clean_text

RawOrder = tuple[str, str, int, int]


@dataclass(frozen=True)
class Order:
    customer: str
    item: str
    quantity: int
    unit_price: int


def parse_order(row: RawOrder) -> Order:
    customer, item, quantity, unit_price = row
    customer = clean_text(customer)
    item = clean_text(item)
    if not customer or not item or quantity < 1 or unit_price < 0:
        raise ValueError("Invalid order")
    return Order(customer, item, quantity, unit_price)
