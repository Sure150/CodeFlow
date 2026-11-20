from collections.abc import Callable

from helpers import normalize as normalize_text
from model.sales_summary import SalesSummary


def normalize(value: str) -> str:
    return value.upper()


def format_message(value: str, callback: Callable[[str], str]) -> str:
    cleaned = normalize_text(value)
    display = normalize(cleaned)
    return callback(display)


def format_amount(cents: int) -> str:
    return f"${cents // 100}.{cents % 100:02d}"


def rank_customers(totals: dict[str, int]) -> list[tuple[str, int]]:
    return sorted(totals.items(), key=lambda customer: (-customer[1], customer[0]))


def render_customer_row(customer: str, total: int) -> str:
    return f"{customer}: {format_amount(total)}"


def render_totals(summary: SalesSummary) -> str:
    return (
        f"Orders: {summary.order_count} valid, {summary.rejected_count} rejected\n"
        f"Revenue: {format_amount(summary.revenue)}"
    )


def render_report(summary: SalesSummary) -> str:
    title = format_message(" order summary ", str)
    lines = [title, render_totals(summary), "", "By customer:"]
    for customer, total in rank_customers(summary.customer_totals):
        lines.append(render_customer_row(customer, total))
    return "\n".join(lines)
