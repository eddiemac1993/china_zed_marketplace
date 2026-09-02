import logging

from allauth.account.signals import user_signed_up
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.db.models.signals import post_save
from django.dispatch import receiver
from webpush import send_user_notification

from .models import Product, Order, OrderCheckpoint, DeliveryJob, Biker, MarketplaceEvent, calculate_biker_payout

logger = logging.getLogger(__name__)


@receiver(user_signed_up)
def notify_owner_about_google_signup(sender, request, user, **kwargs):
    sociallogin = kwargs.get("sociallogin")
    if not sociallogin or sociallogin.account.provider != "google":
        return
    if not settings.SITE_OWNER_EMAIL:
        return

    try:
        send_mail(
            subject="New Google signup on ChinaZed",
            message=(
                "A new customer joined ChinaZed using Google.\n\n"
                f"Name: {user.get_full_name() or 'Not provided'}\n"
                f"Email: {user.email}\n"
                f"Username: {user.get_username()}\n"
                f"Joined: {user.date_joined:%Y-%m-%d %H:%M %Z}\n"
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[settings.SITE_OWNER_EMAIL],
            fail_silently=False,
        )
    except Exception:
        logger.exception("Could not notify site owner about Google signup for user %s", user.pk)


@receiver(post_save, sender=Order)
def record_completed_order(sender, instance, **kwargs):
    if instance.status != "successful":
        return
    MarketplaceEvent.objects.get_or_create(
        event_type="completed_order",
        order=instance,
        defaults={
            "user": instance.user,
            "value": instance.total_price,
        },
    )


@receiver(post_save, sender=Product)
def notify_users_about_new_product(sender, instance, created, **kwargs):
    if not created or not instance.is_available:
        return

    payload = {
        "head": f"New on ChinaZed: {instance.name}",
        "body": "A new item is available. Tap to view it.",
        "icon": instance.display_image_url or "/static/core/images/chinazed-icon-192.png",
        "url": f"/product/{instance.slug}/",
    }

    users = get_user_model().objects.filter(
        webpush_info__isnull=False,
        is_active=True,
    ).distinct()

    for user in users.iterator():
        try:
            send_user_notification(user=user, payload=payload, ttl=86400)
        except Exception:
            logger.exception("Web push failed for user %s", user.pk)


@receiver(post_save, sender=OrderCheckpoint)
def handle_new_order_checkpoint(sender, instance, created, **kwargs):
    if not created:
        return

    order = instance.order

    # Once a direct-delivery order reaches its staging centre, open it up as
    # an available job for bikers registered to that centre.
    if instance.checkpoint_type == "arrived_centre" and order.delivery_method == "direct":
        if not DeliveryJob.objects.filter(order=order).exists() and order.collection_centre_id:
            payout, percentage = calculate_biker_payout(order.delivery_fee)
            DeliveryJob.objects.create(
                order=order,
                centre=order.collection_centre,
                status="available",
                biker_fee_percentage_used=percentage,
                biker_payout_amount=payout,
            )

    if instance.notify_customer and order.user_id:
        payload = {
            "head": f"Order #{order.id} update",
            "body": instance.message or instance.get_checkpoint_type_display(),
            "url": f"/order/{order.id}/",
        }
        try:
            send_user_notification(user=order.user, payload=payload, ttl=172800)
        except Exception:
            logger.exception("Web push failed for user %s (order checkpoint)", order.user_id)


@receiver(post_save, sender=DeliveryJob)
def notify_bikers_of_new_job(sender, instance, created, **kwargs):
    if not created or instance.status != "available":
        return

    bikers = Biker.objects.filter(
        home_centre=instance.centre,
        is_approved=True,
        is_active=True,
        user__webpush_info__isnull=False,
    ).distinct()

    payload = {
        "head": "New delivery job available",
        "body": f"A delivery job is available at {instance.centre.name}. Open the app to accept it.",
        "url": "/biker/dashboard/",
    }

    for biker in bikers.iterator():
        try:
            send_user_notification(user=biker.user, payload=payload, ttl=43200)
        except Exception:
            logger.exception("Web push failed for biker %s (new job)", biker.user_id)
