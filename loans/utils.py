"""Shared helpers for the loan-management module."""
from decimal import Decimal, ROUND_HALF_UP
from functools import wraps

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.shortcuts import redirect

TWO_PLACES = Decimal("0.01")

LOAN_ADMIN_GROUP = "Loan Admins"


def money(value) -> Decimal:
    """Coerce anything numeric to a 2dp Decimal (bankers rounding off)."""
    if not isinstance(value, Decimal):
        value = Decimal(str(value or 0))
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def is_loan_staff(user) -> bool:
    """Staff can view every screen in the module."""
    return bool(user and user.is_authenticated and user.is_staff)


def is_loan_admin(user) -> bool:
    """Admins can create/edit/delete loans, take payments and change settings."""
    if not (user and user.is_authenticated):
        return False
    if user.is_superuser:
        return True
    return user.groups.filter(name=LOAN_ADMIN_GROUP).exists()


def loan_staff_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), login_url="login")
        if not is_loan_staff(request.user):
            messages.error(request, "You do not have access to Loan Management.")
            return redirect("home")
        return view_func(request, *args, **kwargs)

    return _wrapped


def loan_admin_required(view_func):
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), login_url="login")
        if not is_loan_admin(request.user):
            messages.error(
                request,
                "Only loan admins can create or change loans, payments and settings.",
            )
            return redirect("loans:dashboard")
        return view_func(request, *args, **kwargs)

    return _wrapped
