from django import template
from django.utils import timezone
from core.models import Advertisement
import random

register = template.Library()

@register.simple_tag
def get_current_ads():
    hour = timezone.localtime().hour
    return Advertisement.objects.filter(hour_slot=hour, is_active=True)


@register.simple_tag
def mix_product_ads(products, ads):
    """Return product and sponsored cards in a fresh random order per render."""
    product_cards = [{"kind": "product", "item": product} for product in products]
    ad_list = list(ads or [])
    if not product_cards or not ad_list:
        return product_cards

    # Keep the grid useful: at most one sponsored card for every five products.
    maximum_ads = max(1, (len(product_cards) + 4) // 5)
    chosen_ads = random.sample(ad_list, min(len(ad_list), maximum_ads))
    cards = product_cards + [{"kind": "ad", "item": ad} for ad in chosen_ads]
    random.shuffle(cards)
    return cards
