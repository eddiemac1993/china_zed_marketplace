from django.db.models import Avg, Count, Q, Sum


def with_display_annotations(queryset):
    """Annotate a Product queryset with read-only display fields used by
    product cards: units sold (from non-cancelled order items) and the
    average buyer rating. Does not touch cart/order/payment logic.
    """
    return queryset.annotate(
        sold_count=Sum(
            "orderitem__quantity",
            filter=~Q(orderitem__order__status="cancelled"),
        ),
        rating_avg=Avg("reviews__rating", filter=Q(reviews__is_approved=True)),
        rating_count=Count(
            "reviews", filter=Q(reviews__is_approved=True), distinct=True
        ),
    )


SORT_OPTIONS = {
    "newest": "-created_at",
    "price_low": "rmb_price",
    "price_high": "-rmb_price",
    "popular": "-sold_count",
}


def apply_sort(queryset, sort_key):
    ordering = SORT_OPTIONS.get(sort_key)
    if not ordering:
        return queryset
    if sort_key == "popular":
        queryset = with_display_annotations(queryset)
    return queryset.order_by(ordering)
