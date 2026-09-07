"""Rules for the in-app self-service Quick Loan: who can borrow, and how much.

Growth model
------------
A first-time borrower can request up to ``app_loan_starting_limit``. Every time
they repay an app loan **on time** (no late payment on it), their limit rises to
``that loan's amount x app_loan_growth_multiplier`` if that's higher than their
current limit - capped at ``app_loan_max_limit``. A loan repaid late still clears
the debt but does not raise the limit. Only one open app loan (or pending
request) is allowed at a time.
"""
from decimal import Decimal

from .models import Loan, LoanCustomer, LoanRequest, LoanSettings
from .utils import money

ZERO = Decimal("0")


def get_or_create_customer(user):
    """Find/create the LoanCustomer linked to this site account, keeping the
    display name in step with their site profile."""
    full_name = user.get_full_name() or user.get_username()
    customer, created = LoanCustomer.objects.get_or_create(
        user=user, defaults={"full_name": full_name}
    )
    if not created and customer.full_name != full_name:
        customer.full_name = full_name
        customer.save(update_fields=["full_name", "updated_at"])
    return customer


def _grown(amount, cfg):
    return money(min(cfg.app_loan_max_limit, amount * cfg.app_loan_growth_multiplier))


def eligible_limit(user):
    """The most this user can request right now."""
    cfg = LoanSettings.load()
    limit = money(cfg.app_loan_starting_limit)
    completed = (
        Loan.objects.filter(customer__user=user, source=Loan.APP, status=Loan.PAID)
        .prefetch_related("payments")
    )
    for loan in completed:
        paid_on_time = not any(p.paid_late for p in loan.payments.all())
        if paid_on_time:
            limit = max(limit, _grown(loan.principal, cfg))
    return limit


def next_limit_preview(user):
    """What the limit would become if the current open loan is repaid on time
    - so the customer can see what good repayment unlocks. None if no open loan."""
    cfg = LoanSettings.load()
    current = (
        Loan.objects.filter(customer__user=user, source=Loan.APP)
        .exclude(status=Loan.PAID)
        .order_by("-issue_date")
        .first()
    )
    if not current:
        return None
    return max(eligible_limit(user), _grown(current.principal, cfg))


def repayment_stats(user):
    cfg = LoanSettings.load()
    completed = (
        Loan.objects.filter(customer__user=user, source=Loan.APP, status=Loan.PAID)
        .prefetch_related("payments")
    )
    repaid = 0
    repaid_on_time = 0
    for loan in completed:
        repaid += 1
        if not any(p.paid_late for p in loan.payments.all()):
            repaid_on_time += 1
    limit = eligible_limit(user)
    return {
        "limit": limit,
        "starting_limit": money(cfg.app_loan_starting_limit),
        "max_limit": money(cfg.app_loan_max_limit),
        "multiplier": cfg.app_loan_growth_multiplier,
        "loans_repaid": repaid,
        "loans_repaid_on_time": repaid_on_time,
        "next_limit": next_limit_preview(user),
        "at_max": limit >= cfg.app_loan_max_limit,
        "progress_pct": (
            min(100, round(limit / cfg.app_loan_max_limit * 100))
            if cfg.app_loan_max_limit else 0
        ),
    }


def blocking_reason(user) -> str:
    """Empty string if the user can apply right now, else why not."""
    cfg = LoanSettings.load()
    if not cfg.app_loans_enabled:
        return "Quick Loans are currently unavailable."
    customer = LoanCustomer.objects.filter(user=user).first()
    if customer and customer.status == LoanCustomer.BLACKLISTED:
        return "Your loan account is on hold. Please contact support."
    if Loan.objects.filter(customer__user=user, source=Loan.APP).exclude(status=Loan.PAID).exists():
        return "You already have an active loan. Settle it before requesting another."
    if LoanRequest.objects.filter(user=user, status=LoanRequest.PENDING).exists():
        return "You already have a loan request waiting for review."
    return ""
