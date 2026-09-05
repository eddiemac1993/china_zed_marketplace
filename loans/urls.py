from django.urls import path

from . import views

app_name = "loans"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),

    path("customers/", views.customer_list, name="customer_list"),
    path("customers/new/", views.customer_create, name="customer_create"),
    path("customers/<int:pk>/", views.customer_detail, name="customer_detail"),
    path("customers/<int:pk>/edit/", views.customer_edit, name="customer_edit"),
    path("customers/<int:pk>/delete/", views.customer_delete, name="customer_delete"),

    path("loans/", views.loan_list, name="loan_list"),
    path("loans/new/", views.loan_create, name="loan_create"),
    path("loans/<int:pk>/", views.loan_detail, name="loan_detail"),
    path("loans/<int:pk>/edit/", views.loan_edit, name="loan_edit"),
    path("loans/<int:pk>/top-up/", views.loan_topup, name="loan_topup"),
    path("loans/<int:pk>/delete/", views.loan_delete, name="loan_delete"),
    path("loans/<int:loan_pk>/payment/", views.payment_create, name="payment_create"),
    path("topups/<int:pk>/delete/", views.topup_delete, name="topup_delete"),

    path("payments/", views.payment_list, name="payment_list"),
    path("payments/<int:pk>/receipt.pdf", views.payment_receipt_pdf, name="payment_receipt"),
    path("payments/<int:pk>/delete/", views.payment_delete, name="payment_delete"),

    path("reports/", views.reports, name="reports"),
    path("settings/", views.settings_view, name="settings"),
    path("notifications/", views.notifications_feed, name="notifications_feed"),

    # customer-facing Quick Loan
    path("apply/", views.apply_loan, name="apply"),
    path("my/", views.my_loans, name="my_loans"),
    path("my/<int:pk>/", views.my_loan_detail, name="my_loan_detail"),
    path("my/<int:pk>/pay/", views.request_payment, name="request_payment"),

    # staff approval queue
    path("requests/", views.request_queue, name="request_queue"),
    path("requests/loan/<int:pk>/approve/", views.approve_loan_request, name="approve_loan_request"),
    path("requests/loan/<int:pk>/decline/", views.decline_loan_request, name="decline_loan_request"),
    path("requests/payment/<int:pk>/approve/", views.approve_payment_request, name="approve_payment_request"),
    path("requests/payment/<int:pk>/decline/", views.decline_payment_request, name="decline_payment_request"),
]
