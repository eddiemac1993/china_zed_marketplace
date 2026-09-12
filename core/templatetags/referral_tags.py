from django import template
from core.referrals import referral_url

register = template.Library()


@register.simple_tag(takes_context=True)
def product_share_url(context, product):
    return referral_url(context["request"], product)
