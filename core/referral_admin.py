from django.contrib import admin, messages
from django.db import transaction
from django.utils import timezone
from .models import Order, ReferralReward


@admin.register(ReferralReward)
class ReferralRewardAdmin(admin.ModelAdmin):
    list_display = ("id", "referrer", "item", "amount", "status", "payout_due", "payment_reference", "paid_at")
    list_filter = ("status", "payout_due")
    search_fields = ("referrer__username", "referrer__email", "item__product_name", "payment_reference")
    list_select_related = ("referrer", "item")
    actions = ("record_payment",)
    readonly_fields = ("item", "referrer", "amount", "status", "earned_at", "payout_due", "paid_at", "paid_by", "created_at")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return self.readonly_fields + (("payment_reference",) if obj and obj.status == "paid" else ())

    @admin.action(description="Record completed month-end payments (reference required)", permissions=["change"])
    def record_payment(self, request, queryset):
        count = 0
        with transaction.atomic():
            # Match reward synchronization's order-before-reward lock order.
            orders = {order.pk: order for order in Order.objects.select_for_update().filter(
                pk__in=queryset.values_list("item__order_id", flat=True)).order_by("pk")}
            for reward in queryset.select_for_update().select_related("item__order"):
                order = orders[reward.item.order_id]
                if (reward.status != "earned" or not reward.payout_due or reward.payout_due > timezone.localdate()
                        or not reward.payment_reference.strip() or order.status != "successful"
                        or not order.deposit_confirmed or not order.balance_paid or order.is_deleted
                        or order.refund_status != "not_required" or reward.item.availability_status == "unavailable"):
                    continue
                reward.status = "paid"
                reward.paid_at = timezone.now()
                reward.paid_by = request.user
                reward.save(update_fields=["status", "paid_at", "paid_by"])
                self.log_change(request, reward, "Recorded external referral payment: " + reward.payment_reference)
                count += 1
        self.message_user(request, f"Recorded {count} payments. Only due, completed, fully paid orders with a payment reference qualify. This action does not transfer money.", messages.INFO)
