"""Capital utilization check - warns (never blocks) when the loan book is
lending out more than the declared Total Capital."""
from decimal import Decimal

from .models import Loan, LoanSettings
from .utils import money

ZERO = Decimal("0")


def capital_status():
    cfg = LoanSettings.load()
    lent_out = money(sum((l.principal for l in Loan.objects.exclude(status=Loan.PAID)), ZERO))
    over = bool(cfg.total_capital) and lent_out > cfg.total_capital
    return {
        "capital": cfg.total_capital,
        "lent_out": lent_out,
        "utilization_pct": (
            round(lent_out / cfg.total_capital * 100) if cfg.total_capital else None
        ),
        "over_capital": over,
        "over_amount": money(lent_out - cfg.total_capital) if over else ZERO,
    }


def capital_warning_text():
    """A one-line warning to tack onto a success message, or '' if within budget."""
    status = capital_status()
    if not status["over_capital"]:
        return ""
    return (
        f" ⚠️ Outstanding loans (K{status['lent_out']}) now exceed your declared "
        f"capital (K{status['capital']}) by K{status['over_amount']}."
    )
