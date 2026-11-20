from repository.order_repository import load_orders
from service.order_service import summarize
from view import report_view


def build_report() -> str:
    rows = load_orders()
    summary = summarize(rows)
    return report_view.render_report(summary)
