"""Product-specific referral attribution and an auditable reward ledger."""
import calendar
from datetime import timedelta
from decimal import Decimal
from urllib.parse import urlencode

from django.core import signing
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

SALT = "chinazed.product-referral.v1"
WINDOW = timedelta(days=30)


def referral_url(request, product):
    from django.urls import reverse
    url = request.build_absolute_uri(reverse("product_detail", args=[product.slug]))
    if request.user.is_authenticated:
        token = signing.dumps({"user": request.user.pk, "product": product.pk}, salt=SALT)
        url += "?" + urlencode({"ref": token})
    return url


def capture_referral(request, product):
    from django.contrib.auth import get_user_model
    token = request.GET.get("ref")
    if not token:
        return
    try:
        data = signing.loads(token, salt=SALT)
        user_id = data["user"]
        if data["product"] != product.pk or user_id == request.user.pk:
            return
        if not get_user_model().objects.filter(pk=user_id, is_active=True).exists():
            return
    except (signing.BadSignature, KeyError, TypeError, ValueError):
        return
    referrals = request.session.get("product_referrals", {})
    now = timezone.now().timestamp()
    referrals = {k: v for k, v in referrals.items() if v["expires"] > now}
    # Last valid shared link wins for this product; expire 30 days after visiting.
    referrals[str(product.pk)] = {"user": user_id, "expires": now + WINDOW.total_seconds()}
    request.session["product_referrals"] = dict(list(referrals.items())[-100:])


def referrer_for(request, product):
    from django.contrib.auth import get_user_model
    data = request.session.get("product_referrals", {}).get(str(product.pk))
    if not data or data["expires"] <= timezone.now().timestamp() or data["user"] == request.user.pk:
        return None
    return get_user_model().objects.filter(pk=data["user"], is_active=True).first()


@transaction.atomic
def sync_order_rewards(order_id):
    from .models import Order, ReferralReward, money
    order = Order.objects.select_for_update().get(pk=order_id)
    eligible = (order.status == "successful" and order.deposit_confirmed and order.balance_paid
                and not order.is_deleted and order.refund_status == "not_required")
    void = order.is_deleted or order.status == "cancelled" or order.refund_status != "not_required"
    for item in order.items.filter(referrer__isnull=False).exclude(referrer_id=order.user_id):
        reward, _ = ReferralReward.objects.get_or_create(
            item=item, defaults={"referrer_id": item.referrer_id, "amount": money(item.line_total * Decimal("0.05"))},
        )
        # Paid entries are immutable payment history, including after a refund.
        if reward.status == "paid":
            continue
        reward.amount = max(Decimal("0.00"), money(item.line_total * Decimal("0.05")))
        item_void = void or item.availability_status == "unavailable" or item.quantity == 0
        reward.status = "void" if item_void else ("earned" if eligible else "pending")
        if reward.status != "earned":
            reward.earned_at = None
            reward.payout_due = None
        elif reward.earned_at is None:
            reward.earned_at = timezone.now()
            date = timezone.localdate()
            reward.payout_due = date.replace(day=calendar.monthrange(date.year, date.month)[1])
        reward.save()


def profile_rewards(user):
    from .models import ReferralReward
    qs = ReferralReward.objects.filter(referrer=user)
    totals = {row["status"]: row["total"] for row in qs.values("status").annotate(total=Sum("amount"))}
    return {"referral_rewards": qs.select_related("item")[:30],
            "referral_pending": totals.get("pending", Decimal("0")),
            "referral_earned": totals.get("earned", Decimal("0")),
            "referral_paid": totals.get("paid", Decimal("0"))}
