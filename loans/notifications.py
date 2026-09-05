"""Push notifications for the loan module, built on the site's existing
django-webpush setup (see core/signals.py for the same pattern)."""
import logging

from django.contrib.auth.models import User
from django.db.models import Q
from webpush import send_user_notification

from .utils import LOAN_ADMIN_GROUP

logger = logging.getLogger("loans.notifications")


def notify_user(user, *, head, body, url, ttl=172800):
    if not user:
        return
    try:
        send_user_notification(
            user=user, payload={"head": head, "body": body, "url": url}, ttl=ttl
        )
    except Exception:
        logger.exception("Loan web push failed for user %s", getattr(user, "pk", None))


def notify_loan_admins(*, head, body, url, ttl=86400):
    """Alert every subscribed Loan Admin / superuser - used when a new
    customer request lands in the queue."""
    admins = (
        User.objects.filter(is_active=True, webpush_info__isnull=False)
        .filter(Q(is_superuser=True) | Q(groups__name=LOAN_ADMIN_GROUP))
        .distinct()
    )
    for admin in admins:
        notify_user(admin, head=head, body=body, url=url, ttl=ttl)
