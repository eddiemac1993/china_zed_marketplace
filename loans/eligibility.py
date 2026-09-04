"""Rules for the in-app self-service Quick Loan: who can borrow, and how much.

Growth model: a first-time borrower can request up to ``app_loan_starting_limit``.
Once they fully repay an app loan, their next ceiling becomes
``max(that loan's amount, starting limit) * app_loan_growth_multiplier``, capped
at ``app_loan_max_limit``. Only one open app loan (or pending request) is allowed
at a time.
"""
from .models import Loan, LoanCustomer, LoanRequest, LoanSettings
from .utils import money


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


def eligible_limit(user):
    """The most this user can request right now."""
    cfg = LoanSettings.load()
    completed = (
        Loan.objects.filter(customer__user=user, source=Loan.APP, status=Loan.PAID)
        .order_by("-paid_date", "-id")
    )
    if not completed.exists():
        return money(cfg.app_loan_starting_limit)
    base = max(completed.first().principal, cfg.app_loan_starting_limit)
    return money(min(cfg.app_loan_max_limit, base * cfg.app_loan_growth_multiplier))


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
