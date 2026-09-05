"""Due-date reminder engine.

Actual SMS / WhatsApp delivery is left as a pluggable hook: by default every
message is written to ``LoanReminderLog`` (channel ``log``) and printed to the
console.  Wire a real gateway by setting ``LOAN_SMS_SENDER`` /
``LOAN_WHATSAPP_SENDER`` in settings to a dotted path of a callable
``fn(phone: str, message: str) -> bool``.
"""
import logging

from django.conf import settings
from django.utils import timezone
from django.utils.module_loading import import_string

from .models import Loan, LoanReminderLog, LoanSettings

logger = logging.getLogger("loans.reminders")


def _load_sender(setting_name):
    path = getattr(settings, setting_name, None)
    if not path:
        return None
    try:
        return import_string(path)
    except ImportError:  # pragma: no cover - configuration error
        logger.warning("Could not import %s = %r", setting_name, path)
        return None


def _deliver(customer, message, cfg):
    """Return (channel, success). Falls back to the audit log."""
    if cfg.whatsapp_enabled:
        sender = _load_sender("LOAN_WHATSAPP_SENDER")
        if sender:
            return "whatsapp", bool(sender(customer.phone, message))
    if cfg.sms_enabled:
        sender = _load_sender("LOAN_SMS_SENDER")
        if sender:
            return "sms", bool(sender(customer.phone, message))
    logger.info("[loan reminder] %s (%s): %s", customer.full_name, customer.phone, message)
    return "log", True


def _message_for(loan, kind, cfg):
    name = loan.customer.full_name.split()[0]
    amount = loan.balance
    when = loan.due_date.strftime("%d %b %Y")
    if kind == LoanReminderLog.OVERDUE:
        body = (
            f"Hi {name}, your loan {loan.reference} of K{amount} was due on {when} "
            f"and is now overdue. Please settle it as soon as possible."
        )
    elif kind == LoanReminderLog.ON_DUE:
        body = f"Hi {name}, your loan {loan.reference} balance of K{amount} is due today ({when})."
    else:
        days = "3 days" if kind == LoanReminderLog.THREE_DAYS else "1 day"
        body = (
            f"Hi {name}, a reminder that your loan {loan.reference} balance of "
            f"K{amount} is due in {days} on {when}."
        )
    signature = cfg.reminder_signature or cfg.business_name
    return f"{body}\n- {signature}"


def due_kind_for(loan, cfg):
    """Which reminder (if any) applies to this loan today."""
    days = loan.days_until_due
    if days == 3 and cfg.remind_3_days_before:
        return LoanReminderLog.THREE_DAYS
    if days == 1 and cfg.remind_1_day_before:
        return LoanReminderLog.ONE_DAY
    if days == 0 and cfg.remind_on_due_date:
        return LoanReminderLog.ON_DUE
    if days < 0 and cfg.remind_when_overdue:
        return LoanReminderLog.OVERDUE
    return None


def run_reminders(*, dry_run=False):
    """Send every reminder that is due today. Returns a list of result dicts.

    Also refreshes every open loan's status first (active/due soon/overdue),
    which in turn re-evaluates each customer's Good/Late/Blacklisted label -
    without this, a loan that quietly crosses its due date only gets
    re-checked the next time someone edits it or takes a payment on it.
    """
    cfg = LoanSettings.load()
    results = []
    open_loans = Loan.objects.exclude(status=Loan.PAID).select_related("customer")
    if not dry_run:
        for loan in open_loans:
            loan.refresh_status()
    for loan in open_loans:
        if loan.is_fully_paid:
            continue
        kind = due_kind_for(loan, cfg)
        if not kind:
            continue
        if LoanReminderLog.objects.filter(loan=loan, kind=kind).exists():
            continue
        message = _message_for(loan, kind, cfg)
        entry = {
            "loan": loan.reference,
            "customer": loan.customer.full_name,
            "kind": kind,
            "message": message,
        }
        if dry_run:
            entry["channel"] = "dry-run"
            entry["success"] = None
            results.append(entry)
            continue
        channel, success = _deliver(loan.customer, message, cfg)
        LoanReminderLog.objects.create(
            loan=loan,
            customer=loan.customer,
            kind=kind,
            channel=channel,
            message=message,
            success=success,
        )
        entry["channel"] = channel
        entry["success"] = success
        results.append(entry)
    return results
