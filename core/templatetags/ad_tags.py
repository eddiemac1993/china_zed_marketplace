from django import template
from django.utils import timezone
from core.models import Advertisement

register = template.Library()

@register.simple_tag
def get_current_ads():
    hour = timezone.localtime().hour
    return Advertisement.objects.filter(hour_slot=hour, is_active=True)