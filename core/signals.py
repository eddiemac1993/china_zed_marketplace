import logging

from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver
from webpush import send_user_notification

from .models import Product

logger = logging.getLogger(__name__)


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
