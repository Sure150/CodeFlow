from collections.abc import Iterable

from model.order import Order, RawOrder, parse_order
from model.sales_summary import SalesSummary

from .pricing_service import line_total


def collect_orders(rows: Iterable[RawOrder]) -> tuple[list[Order], int]:
    orders = []
    rejected = 0
    for row in rows:
        try:
            orders.append(parse_order(row))
        except ValueError:
            rejected += 1
    return orders, rejected


def order_total(order: Order) -> int:
    return line_total(order.unit_price, order.quantity)


def total_by_customer(orders: Iterable[Order]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for order in orders:
        totals[order.customer] = totals.get(order.customer, 0) + order_total(order)
    return totals


def summarize(rows: Iterable[RawOrder]) -> SalesSummary:
    orders, rejected_count = collect_orders(rows)
    customer_totals = total_by_customer(orders)
    revenue = sum(customer_totals.values())
    return SalesSummary(len(orders), rejected_count, revenue, customer_totals)
