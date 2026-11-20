from dataclasses import dataclass

@dataclass(frozen=True)
class SalesSummary:
    order_count: int
    rejected_count: int
    revenue: int
    customer_totals: dict[str, int]
