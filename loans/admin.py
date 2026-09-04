from django.contrib import admin

from .models import (
    Loan,
    LoanCustomer,
    LoanPayment,
    LoanPaymentRequest,
    LoanReminderLog,
    LoanRequest,
    LoanSettings,
    LoanTopUp,
)


class LoanTopUpInline(admin.TabularInline):
    model = LoanTopUp
    extra = 0
    readonly_fields = ("principal_before", "principal_after", "repayment_after", "created_at")


class LoanPaymentInline(admin.TabularInline):
    model = LoanPayment
    extra = 0
    readonly_fields = ("receipt_number", "balance_after", "paid_late", "created_at")


@admin.register(LoanCustomer)
class LoanCustomerAdmin(admin.ModelAdmin):
    list_display = ("full_name", "phone", "nrc_number", "employer", "status")
    list_filter = ("status",)
    search_fields = ("full_name", "phone", "nrc_number", "employer", "employee_number")


@admin.register(Loan)
class LoanAdmin(admin.ModelAdmin):
    list_display = (
        "reference", "customer", "principal", "interest_rate", "period_weeks",
        "issue_date", "due_date", "status",
    )
    list_filter = ("status", "period_weeks", "payment_method")
    search_fields = ("reference", "customer__full_name", "customer__nrc_number")
    readonly_fields = ("reference", "principal", "receipt_number", "paid_date", "paid_by")
    inlines = [LoanTopUpInline, LoanPaymentInline]


@admin.register(LoanPayment)
class LoanPaymentAdmin(admin.ModelAdmin):
    list_display = ("receipt_number", "loan", "amount_paid", "payment_date", "method", "paid_late")
    list_filter = ("method", "paid_late")
    search_fields = ("receipt_number", "loan__reference", "loan__customer__full_name")
    readonly_fields = ("receipt_number", "balance_after", "paid_late")


@admin.register(LoanReminderLog)
class LoanReminderLogAdmin(admin.ModelAdmin):
    list_display = ("customer", "loan", "kind", "channel", "success", "sent_at")
    list_filter = ("kind", "channel", "success")


@admin.register(LoanSettings)
class LoanSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not LoanSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LoanRequest)
class LoanRequestAdmin(admin.ModelAdmin):
    list_display = ("customer", "user", "amount", "period_weeks", "status", "requested_at")
    list_filter = ("status", "period_weeks")
    search_fields = ("customer__full_name", "user__username", "user__email")
    readonly_fields = ("loan", "decided_at", "decided_by")


@admin.register(LoanPaymentRequest)
class LoanPaymentRequestAdmin(admin.ModelAdmin):
    list_display = ("loan", "user", "amount", "method", "status", "requested_at")
    list_filter = ("status", "method")
    search_fields = ("loan__reference", "user__username", "reference")
    readonly_fields = ("payment", "decided_at", "decided_by")
