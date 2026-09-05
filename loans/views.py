import csv
from datetime import date, timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Sum
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import get_template
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST
from xhtml2pdf import pisa

from .eligibility import blocking_reason, eligible_limit, get_or_create_customer
from .forms import (
    LoanApplicationForm,
    LoanCustomerForm,
    LoanForm,
    LoanPaymentForm,
    LoanPaymentRequestForm,
    LoanSettingsForm,
    LoanTopUpForm,
)
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
from .utils import is_loan_admin, loan_admin_required, loan_staff_required, money

ZERO = Decimal("0")


# --------------------------------------------------------------------------- #
#  metric helpers                                                              #
# --------------------------------------------------------------------------- #
def _month_starts(count=6):
    today = timezone.localdate().replace(day=1)
    months = []
    y, m = today.year, today.month
    for _ in range(count):
        months.append(date(y, m, 1))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return list(reversed(months))


def _sum(qs, field):
    return money(qs.aggregate(t=Sum(field))["t"] or 0)


def dashboard_metrics():
    cfg = LoanSettings.load()
    loans = list(Loan.objects.select_related("customer"))
    payments = LoanPayment.objects.select_related("loan")

    money_lent = money(sum((l.principal for l in loans), ZERO))
    money_collected = _sum(payments, "amount_paid")
    interest_earned = money(sum((l.interest_collected for l in loans), ZERO))
    outstanding = money(sum((l.balance for l in loans if l.status != Loan.PAID), ZERO))
    overdue_loans = [l for l in loans if l.status == Loan.OVERDUE]
    overdue_total = money(sum((l.balance for l in overdue_loans), ZERO))
    active_customers = (
        LoanCustomer.objects.filter(loans__status__in=[Loan.ACTIVE, Loan.DUE_SOON, Loan.OVERDUE])
        .distinct()
        .count()
    )

    cards = [
        {"label": "Total Capital", "value": cfg.total_capital, "icon": "🏦"},
        {"label": "Money Lent Out", "value": money_lent, "icon": "📤"},
        {"label": "Money Collected", "value": money_collected, "icon": "📥"},
        {"label": "Interest Earned", "value": interest_earned, "icon": "📈"},
        {"label": "Outstanding Loans", "value": outstanding, "icon": "⏳"},
        {"label": "Overdue Loans", "value": overdue_total, "icon": "🔴",
         "sub": f"{len(overdue_loans)} loan(s)"},
        {"label": "Profit", "value": interest_earned, "icon": "💰",
         "sub": "Interest collected to date"},
        {"label": "Active Customers", "value": active_customers, "icon": "👥",
         "is_count": True},
    ]

    today = timezone.localdate()
    week_end = today + timedelta(days=7)
    due_today = [l for l in loans if l.status != Loan.PAID and l.due_date == today]
    due_week = [
        l for l in loans
        if l.status != Loan.PAID and today < l.due_date <= week_end
    ]
    recently_paid = (
        Loan.objects.filter(status=Loan.PAID)
        .select_related("customer")
        .order_by("-paid_date", "-id")[:8]
    )

    # charts ------------------------------------------------------------------
    months = _month_starts(6)
    labels = [m.strftime("%b") for m in months]
    profit_series, collect_series = [], []
    for i, start in enumerate(months):
        end = months[i + 1] if i + 1 < len(months) else date(9999, 12, 31)
        month_payments = payments.filter(payment_date__gte=start, payment_date__lt=end)
        collected = ZERO
        profit = ZERO
        for p in month_payments:
            collected += p.amount_paid
            profit += p.interest_part
        collect_series.append(float(money(collected)))
        profit_series.append(float(money(profit)))

    status_counts = {s: 0 for s, _ in Loan.STATUS_CHOICES}
    status_amounts = {s: ZERO for s, _ in Loan.STATUS_CHOICES}
    for l in loans:
        status_counts[l.status] += 1
        status_amounts[l.status] += l.balance

    charts = {
        "labels": labels,
        "profit": profit_series,
        "collections": collect_series,
        "outstanding_labels": ["Active", "Due soon", "Overdue"],
        "outstanding_values": [
            float(money(status_amounts[Loan.ACTIVE])),
            float(money(status_amounts[Loan.DUE_SOON])),
            float(money(status_amounts[Loan.OVERDUE])),
        ],
    }

    return {
        "cfg": cfg,
        "cards": cards,
        "due_today": due_today,
        "due_week": due_week,
        "recently_paid": recently_paid,
        "charts": charts,
        "status_counts": status_counts,
        "pending_loan_requests": LoanRequest.objects.filter(status=LoanRequest.PENDING).count(),
        "pending_payment_requests": LoanPaymentRequest.objects.filter(
            status=LoanPaymentRequest.PENDING
        ).count(),
    }


# --------------------------------------------------------------------------- #
#  dashboard                                                                   #
# --------------------------------------------------------------------------- #
@loan_staff_required
def dashboard(request):
    ctx = dashboard_metrics()
    ctx.update(section="dashboard", can_manage=is_loan_admin(request.user))
    return render(request, "loans/dashboard.html", ctx)


# --------------------------------------------------------------------------- #
#  customers                                                                   #
# --------------------------------------------------------------------------- #
@loan_staff_required
def customer_list(request):
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    customers = LoanCustomer.objects.annotate(loan_count=Count("loans"))
    if q:
        customers = customers.filter(
            Q(full_name__icontains=q)
            | Q(phone__icontains=q)
            | Q(nrc_number__icontains=q)
            | Q(employer__icontains=q)
        )
    if status:
        customers = customers.filter(status=status)
    return render(request, "loans/customers.html", {
        "section": "customers",
        "customers": customers,
        "q": q,
        "status": status,
        "status_choices": LoanCustomer.STATUS_CHOICES,
        "can_manage": is_loan_admin(request.user),
    })


@loan_staff_required
def customer_detail(request, pk):
    customer = get_object_or_404(LoanCustomer, pk=pk)
    loans = customer.loans.prefetch_related("payments", "topups")
    payments = LoanPayment.objects.filter(loan__customer=customer).select_related("loan")
    topups = LoanTopUp.objects.filter(loan__customer=customer).select_related("loan")
    late_payments = payments.filter(paid_late=True)
    return render(request, "loans/customer_detail.html", {
        "section": "customers",
        "customer": customer,
        "loans": loans,
        "payments": payments,
        "topups": topups,
        "late_payments": late_payments,
        "can_manage": is_loan_admin(request.user),
    })


@loan_admin_required
def customer_create(request):
    form = LoanCustomerForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        customer = form.save(commit=False)
        customer.created_by = request.user
        customer.save()
        messages.success(request, f"Customer {customer.full_name} added.")
        return redirect("loans:customer_detail", pk=customer.pk)
    return render(request, "loans/customer_form.html", {
        "section": "customers", "form": form, "is_edit": False,
    })


@loan_admin_required
def customer_edit(request, pk):
    customer = get_object_or_404(LoanCustomer, pk=pk)
    form = LoanCustomerForm(request.POST or None, request.FILES or None, instance=customer)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Customer updated.")
        return redirect("loans:customer_detail", pk=customer.pk)
    return render(request, "loans/customer_form.html", {
        "section": "customers", "form": form, "is_edit": True, "customer": customer,
    })


@loan_admin_required
def customer_delete(request, pk):
    customer = get_object_or_404(LoanCustomer, pk=pk)
    if customer.loans.exists():
        messages.error(
            request,
            f"{customer.full_name} has {customer.loans.count()} loan(s) on record. "
            f"Delete those loans first before deleting the customer.",
        )
        return redirect("loans:customer_detail", pk=customer.pk)
    if request.method == "POST":
        name = customer.full_name
        customer.delete()
        messages.success(request, f"Customer {name} deleted.")
        return redirect("loans:customer_list")
    return render(request, "loans/confirm_delete_item.html", {
        "section": "customers",
        "title": f"Delete {customer.full_name}?",
        "body": f"You are about to permanently delete the customer record for {customer.full_name}. They have no loans on file, so this is safe.",
        "cancel_url": reverse("loans:customer_detail", args=[customer.pk]),
    })


# --------------------------------------------------------------------------- #
#  loans                                                                       #
# --------------------------------------------------------------------------- #
@loan_staff_required
def loan_list(request):
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()
    customer_id = request.GET.get("customer", "").strip()
    month = request.GET.get("month", "").strip()
    rate = request.GET.get("rate", "").strip()

    loans = Loan.objects.select_related("customer")
    if q:
        loans = loans.filter(
            Q(customer__full_name__icontains=q)
            | Q(customer__phone__icontains=q)
            | Q(customer__nrc_number__icontains=q)
            | Q(customer__employer__icontains=q)
            | Q(reference__icontains=q)
        )
    if status:
        loans = loans.filter(status=status)
    if customer_id.isdigit():
        loans = loans.filter(customer_id=int(customer_id))
    if month:
        try:
            y, m = month.split("-")
            loans = loans.filter(issue_date__year=int(y), issue_date__month=int(m))
        except ValueError:
            pass
    if rate:
        try:
            loans = loans.filter(interest_rate=Decimal(rate))
        except Exception:
            pass

    return render(request, "loans/loans.html", {
        "section": "loans",
        "loans": loans,
        "q": q, "status": status, "customer_id": customer_id,
        "month": month, "rate": rate,
        "status_choices": Loan.STATUS_CHOICES,
        "customers": LoanCustomer.objects.all(),
        "rates": Loan.objects.values_list("interest_rate", flat=True).distinct(),
        "can_manage": is_loan_admin(request.user),
    })


@loan_staff_required
def loan_detail(request, pk):
    loan = get_object_or_404(
        Loan.objects.select_related("customer").prefetch_related("payments", "topups", "reminders"),
        pk=pk,
    )
    return render(request, "loans/loan_detail.html", {
        "section": "loans",
        "loan": loan,
        "can_manage": is_loan_admin(request.user),
    })


@loan_admin_required
def loan_create(request):
    cfg = LoanSettings.load()
    initial = {}
    prefill_customer = request.GET.get("customer")
    if prefill_customer and prefill_customer.isdigit():
        initial["customer"] = prefill_customer
    form = LoanForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        loan = form.save(commit=False)
        loan.principal = loan.original_principal
        loan.created_by = request.user
        loan.save()
        loan.refresh_status()
        messages.success(request, f"Loan {loan.reference} created for {loan.customer.full_name}.")
        return redirect("loans:loan_detail", pk=loan.pk)
    return render(request, "loans/loan_form.html", {
        "section": "loans",
        "form": form,
        "rate_map": _rate_map(cfg),
    })


def _rate_map(cfg):
    return {
        1: cfg.interest_1_week, 2: cfg.interest_2_weeks,
        3: cfg.interest_3_weeks, 4: cfg.interest_4_weeks,
    }


@loan_admin_required
def loan_edit(request, pk):
    loan = get_object_or_404(Loan, pk=pk)
    form = LoanForm(request.POST or None, instance=loan)
    if request.method == "POST" and form.is_valid():
        loan = form.save()
        loan.resync_topup_snapshots()
        loan.refresh_status()
        messages.success(request, f"Loan {loan.reference} updated.")
        return redirect("loans:loan_detail", pk=loan.pk)
    return render(request, "loans/loan_form.html", {
        "section": "loans",
        "form": form,
        "loan": loan,
        "is_edit": True,
        "rate_map": _rate_map(LoanSettings.load()),
    })


@loan_admin_required
def loan_topup(request, pk):
    loan = get_object_or_404(Loan, pk=pk)
    if loan.status == Loan.PAID:
        messages.error(request, "This loan is already paid off and cannot be topped up.")
        return redirect("loans:loan_detail", pk=loan.pk)
    form = LoanTopUpForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        loan.add_topup(
            amount=form.cleaned_data["amount"],
            user=request.user,
            note=form.cleaned_data.get("note", ""),
            date=form.cleaned_data.get("date"),
        )
        messages.success(request, f"Top-up added. New principal K{loan.principal}.")
        return redirect("loans:loan_detail", pk=loan.pk)
    return render(request, "loans/topup_form.html", {
        "section": "loans", "loan": loan, "form": form,
    })


@loan_admin_required
def topup_delete(request, pk):
    topup = get_object_or_404(LoanTopUp, pk=pk)
    loan = topup.loan
    if request.method == "POST":
        amount = topup.amount
        topup.delete()
        loan.resync_topup_snapshots()
        loan.refresh_status()
        messages.success(request, f"Top-up of K{amount} removed. Principal is now K{loan.principal}.")
        return redirect("loans:loan_detail", pk=loan.pk)
    return render(request, "loans/confirm_delete_item.html", {
        "section": "loans",
        "title": f"Delete top-up of K{topup.amount}?",
        "body": (
            f"You are about to permanently delete the K{topup.amount} top-up "
            f"({topup.date}) on loan {loan.reference}. The loan's principal and "
            f"repayment will drop back accordingly."
        ),
        "cancel_url": reverse("loans:loan_detail", args=[loan.pk]),
    })


@loan_admin_required
def loan_delete(request, pk):
    loan = get_object_or_404(Loan, pk=pk)
    next_url = request.POST.get("next") or request.GET.get("next", "")
    safe_next = (
        next_url
        if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()})
        else ""
    )
    if request.method == "POST":
        ref = loan.reference
        loan.delete()
        messages.success(request, f"Loan {ref} deleted.")
        return redirect(safe_next or "loans:loan_list")
    return render(request, "loans/confirm_delete.html", {
        "section": "loans", "loan": loan, "next": safe_next,
    })


# --------------------------------------------------------------------------- #
#  payments                                                                    #
# --------------------------------------------------------------------------- #
@loan_staff_required
def payment_list(request):
    payments = LoanPayment.objects.select_related("loan", "loan__customer")
    q = request.GET.get("q", "").strip()
    if q:
        payments = payments.filter(
            Q(loan__customer__full_name__icontains=q)
            | Q(receipt_number__icontains=q)
            | Q(loan__reference__icontains=q)
        )
    return render(request, "loans/payments.html", {
        "section": "payments",
        "payments": payments[:300],
        "q": q,
        "total": _sum(payments, "amount_paid"),
        "can_manage": is_loan_admin(request.user),
    })


@loan_admin_required
def payment_create(request, loan_pk):
    loan = get_object_or_404(Loan, pk=loan_pk)
    if loan.status == Loan.PAID:
        messages.info(request, "This loan is already fully paid.")
        return redirect("loans:loan_detail", pk=loan.pk)
    form = LoanPaymentForm(request.POST or None, loan=loan)
    if request.method == "POST" and form.is_valid():
        payment = form.save(commit=False)
        payment.loan = loan
        payment.created_by = request.user
        payment.officer = (
            request.user.get_full_name() or request.user.get_username()
        )
        payment.save()
        loan.refresh_from_db()
        if loan.status == Loan.PAID:
            messages.success(
                request,
                f"Payment received. Loan {loan.reference} is now PAID. "
                f"Receipt {payment.receipt_number}.",
            )
        else:
            messages.success(
                request,
                f"Payment received. Balance K{loan.balance}. Receipt {payment.receipt_number}.",
            )
        return redirect("loans:loan_detail", pk=loan.pk)
    return render(request, "loans/payment_form.html", {
        "section": "payments", "loan": loan, "form": form,
    })


@loan_admin_required
def payment_delete(request, pk):
    payment = get_object_or_404(LoanPayment, pk=pk)
    loan = payment.loan
    if request.method == "POST":
        receipt = payment.receipt_number
        amount = payment.amount_paid
        payment.delete()
        loan.refresh_status()
        messages.success(
            request,
            f"Payment {receipt} (K{amount}) deleted. Loan balance is now K{loan.balance}.",
        )
        return redirect("loans:loan_detail", pk=loan.pk)
    return render(request, "loans/confirm_delete_item.html", {
        "section": "loans",
        "title": f"Delete payment {payment.receipt_number}?",
        "body": (
            f"You are about to permanently delete payment {payment.receipt_number} "
            f"(K{payment.amount_paid}, {payment.payment_date}) on loan {loan.reference}. "
            f"The loan's balance and status will be recalculated."
        ),
        "cancel_url": reverse("loans:loan_detail", args=[loan.pk]),
    })


@loan_staff_required
def payment_receipt_pdf(request, pk):
    payment = get_object_or_404(
        LoanPayment.objects.select_related("loan", "loan__customer"), pk=pk
    )
    template = get_template("loans/receipt_pdf.html")
    html = template.render({
        "payment": payment,
        "loan": payment.loan,
        "customer": payment.loan.customer,
        "cfg": LoanSettings.load(),
        "generated": timezone.now(),
    })
    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = (
        f'attachment; filename="receipt-{payment.receipt_number}.pdf"'
    )
    if pisa.CreatePDF(html, dest=response).err:
        return HttpResponse("PDF generation failed", status=500)
    return response


# --------------------------------------------------------------------------- #
#  reports                                                                     #
# --------------------------------------------------------------------------- #
def _report_range(period, anchor):
    if period == "daily":
        return anchor, anchor, anchor.strftime("%d %b %Y")
    if period == "weekly":
        start = anchor - timedelta(days=anchor.weekday())
        return start, start + timedelta(days=6), f"Week of {start.strftime('%d %b %Y')}"
    if period == "yearly":
        return date(anchor.year, 1, 1), date(anchor.year, 12, 31), str(anchor.year)
    # monthly (default)
    start = anchor.replace(day=1)
    nxt = (start + timedelta(days=32)).replace(day=1)
    return start, nxt - timedelta(days=1), start.strftime("%B %Y")


def report_data(period, anchor, paid_filter=""):
    start, end, label = _report_range(period, anchor)
    cfg = LoanSettings.load()

    loans_in = Loan.objects.filter(issue_date__gte=start, issue_date__lte=end)
    if paid_filter == "paid":
        loans_in = loans_in.filter(status=Loan.PAID)
    elif paid_filter == "unpaid":
        loans_in = loans_in.exclude(status=Loan.PAID)
    loans_in = loans_in.select_related("customer")
    loans_in_list = list(loans_in)
    payments_in = LoanPayment.objects.filter(
        payment_date__gte=start, payment_date__lte=end
    ).select_related("loan")

    loans_given = money(sum((l.principal for l in loans_in_list), ZERO))
    interest_expected = money(sum((l.interest_amount for l in loans_in_list), ZERO))
    collections = _sum(payments_in, "amount_paid")
    profit = money(sum((p.interest_part for p in payments_in), ZERO))
    outstanding = money(
        sum((l.balance for l in Loan.objects.exclude(status=Loan.PAID)), ZERO)
    )

    # totals for exactly the filtered "Loans issued in period" list below
    loan_totals = {
        "principal": loans_given,
        "interest": interest_expected,
        "repayment": money(sum((l.total_repayment for l in loans_in_list), ZERO)),
        "paid": money(sum((l.amount_paid for l in loans_in_list), ZERO)),
        "balance": money(sum((l.balance for l in loans_in_list), ZERO)),
    }

    rows = [
        ("Capital", cfg.total_capital),
        ("Loans given", loans_given),
        ("Interest (expected on new loans)", interest_expected),
        ("Collections", collections),
        ("Outstanding (book total)", outstanding),
        ("Profit (interest collected)", profit),
    ]
    return {
        "period": period, "label": label, "start": start, "end": end,
        "paid_filter": paid_filter,
        "loan_totals": loan_totals,
        "loan_count": len(loans_in_list),
        "payment_count": payments_in.count(),
        "rows": rows,
        "loans_in": loans_in_list,
        "payments_in": payments_in,
    }


@loan_staff_required
def reports(request):
    period = request.GET.get("period", "monthly")
    if period not in {"daily", "weekly", "monthly", "yearly"}:
        period = "monthly"
    anchor_str = request.GET.get("date", "")
    try:
        anchor = date.fromisoformat(anchor_str) if anchor_str else timezone.localdate()
    except ValueError:
        anchor = timezone.localdate()

    paid_filter = request.GET.get("paid", "")
    if paid_filter not in {"", "paid", "unpaid"}:
        paid_filter = ""
    paid_label = {"paid": "Paid loans only", "unpaid": "Unpaid loans only"}.get(
        paid_filter, "All loans"
    )

    data = report_data(period, anchor, paid_filter)
    export = request.GET.get("export", "")

    if export == "csv":
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="loan-report-{period}-{data["start"]}.csv"'
        )
        writer = csv.writer(response)
        writer.writerow([f"{data['period'].title()} report", data["label"]])
        writer.writerow([paid_label])
        writer.writerow([])
        writer.writerow(["Metric", "Amount (K)"])
        for name, value in data["rows"]:
            writer.writerow([name, value])
        writer.writerow([])
        writer.writerow([f"Loans issued in period ({paid_label})"])
        writer.writerow([
            "Reference", "Customer", "Issue date", "Principal", "Interest",
            "Repayment", "Paid", "Balance", "Status",
        ])
        for loan in data["loans_in"]:
            writer.writerow([
                loan.reference, loan.customer.full_name, loan.issue_date,
                loan.principal, loan.interest_amount, loan.total_repayment,
                loan.amount_paid, loan.balance, loan.get_status_display(),
            ])
        totals = data["loan_totals"]
        writer.writerow([
            f"Total ({data['loan_count']})", "", "",
            totals["principal"], totals["interest"], totals["repayment"],
            totals["paid"], totals["balance"], "",
        ])
        return response

    if export == "pdf":
        template = get_template("loans/report_pdf.html")
        html = template.render({
            **data, "cfg": LoanSettings.load(), "generated": timezone.now(),
            "paid_label": paid_label,
        })
        response = HttpResponse(content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="loan-report-{period}-{data["start"]}.pdf"'
        )
        if pisa.CreatePDF(html, dest=response).err:
            return HttpResponse("PDF generation failed", status=500)
        return response

    return render(request, "loans/reports.html", {
        "section": "reports",
        "period": period,
        "anchor": anchor,
        "paid_label": paid_label,
        "print_mode": export == "print",
        "can_manage": is_loan_admin(request.user),
        **data,
    })


# --------------------------------------------------------------------------- #
#  settings + notifications                                                    #
# --------------------------------------------------------------------------- #
@loan_admin_required
def settings_view(request):
    cfg = LoanSettings.load()
    form = LoanSettingsForm(request.POST or None, instance=cfg)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Loan settings saved.")
        return redirect("loans:settings")
    return render(request, "loans/settings.html", {
        "section": "settings", "form": form, "cfg": cfg,
    })


@loan_staff_required
def notifications_feed(request):
    today = timezone.localdate()
    since = timezone.now() - timedelta(days=7)
    items = []

    for loan in Loan.objects.filter(status=Loan.OVERDUE).select_related("customer")[:20]:
        items.append({
            "type": "overdue", "icon": "🔴",
            "text": f"{loan.customer.full_name} — loan {loan.reference} overdue (K{loan.balance})",
            "url": f"/loans/loans/{loan.pk}/",
        })
    for loan in Loan.objects.exclude(status=Loan.PAID).filter(due_date=today).select_related("customer"):
        items.append({"type": "due_today", "icon": "🟡",
                      "text": f"{loan.customer.full_name} — loan {loan.reference} due today",
                      "url": f"/loans/loans/{loan.pk}/"})
    for p in LoanPayment.objects.filter(created_at__gte=since).select_related("loan__customer")[:15]:
        items.append({"type": "payment", "icon": "📥",
                      "text": f"Payment K{p.amount_paid} from {p.loan.customer.full_name} ({p.receipt_number})",
                      "url": f"/loans/loans/{p.loan.pk}/"})
    for l in Loan.objects.filter(created_at__gte=since).select_related("customer")[:15]:
        items.append({"type": "new_loan", "icon": "🆕",
                      "text": f"New loan {l.reference} — {l.customer.full_name} (K{l.principal})",
                      "url": f"/loans/loans/{l.pk}/"})
    for t in LoanTopUp.objects.filter(created_at__gte=since).select_related("loan__customer")[:15]:
        items.append({"type": "topup", "icon": "➕",
                      "text": f"Top-up K{t.amount} on {t.loan.reference} — {t.loan.customer.full_name}",
                      "url": f"/loans/loans/{t.loan.pk}/"})
    for lr in LoanRequest.objects.filter(status=LoanRequest.PENDING).select_related("customer")[:15]:
        items.append({"type": "loan_request", "icon": "🙋",
                      "text": f"Quick Loan request: K{lr.amount} — {lr.customer.full_name}",
                      "url": "/loans/requests/"})
    for pr in LoanPaymentRequest.objects.filter(status=LoanPaymentRequest.PENDING).select_related("loan__customer")[:15]:
        items.append({"type": "payment_request", "icon": "🙋",
                      "text": f"Payment claim: K{pr.amount} — {pr.loan.customer.full_name} ({pr.loan.reference})",
                      "url": "/loans/requests/"})

    return JsonResponse({"count": len(items), "items": items})


# --------------------------------------------------------------------------- #
#  customer-facing: Quick Loan (any logged-in site user)                       #
# --------------------------------------------------------------------------- #
def _app_rate_map(cfg):
    return {
        1: cfg.app_interest_1_week, 2: cfg.app_interest_2_weeks,
        3: cfg.app_interest_3_weeks, 4: cfg.app_interest_4_weeks,
    }


@login_required
def apply_loan(request):
    cfg = LoanSettings.load()
    profile_phone = getattr(getattr(request.user, "customer_profile", None), "phone", "").strip()
    if not profile_phone:
        messages.error(
            request,
            "Add your phone number to your profile first — it's the number we'll use "
            "to deposit your loan.",
        )
        return redirect(reverse("profile") + "#customer-profile-form")

    reason = blocking_reason(request.user)
    min_amount = cfg.app_loan_min_amount
    max_amount = eligible_limit(request.user)

    form = LoanApplicationForm(
        request.POST if (request.method == "POST" and not reason) else None,
        min_amount=min_amount, max_amount=max_amount,
    )
    if request.method == "POST" and not reason and form.is_valid():
        customer = get_or_create_customer(request.user)
        rate = cfg.app_rate_for_period(int(form.cleaned_data["period_weeks"]))
        LoanRequest.objects.create(
            user=request.user,
            customer=customer,
            amount=form.cleaned_data["amount"],
            period_weeks=form.cleaned_data["period_weeks"],
            interest_rate=rate,
            payout_number=profile_phone,
            notes=form.cleaned_data.get("notes", ""),
        )
        messages.success(
            request,
            "Loan request submitted. We'll review it and deposit to your number once approved.",
        )
        return redirect("loans:my_loans")

    return render(request, "loans/apply.html", {
        "form": form, "cfg": cfg, "min_amount": min_amount, "max_amount": max_amount,
        "blocking_reason": reason, "profile_phone": profile_phone,
        "rate_map": _app_rate_map(cfg),
    })


@login_required
def my_loans(request):
    customer = LoanCustomer.objects.filter(user=request.user).first()
    loans = (
        Loan.objects.filter(customer=customer, source=Loan.APP).order_by("-issue_date")
        if customer else Loan.objects.none()
    )
    requests_qs = LoanRequest.objects.filter(user=request.user).order_by("-requested_at")[:10]
    outstanding = money(sum((l.balance for l in loans if l.status != Loan.PAID), ZERO))
    return render(request, "loans/my_loans.html", {
        "loans": loans,
        "requests": requests_qs,
        "outstanding": outstanding,
        "eligible_limit": eligible_limit(request.user),
        "blocking_reason": blocking_reason(request.user),
        "min_amount": LoanSettings.load().app_loan_min_amount,
    })


@login_required
def my_loan_detail(request, pk):
    loan = get_object_or_404(Loan.objects.select_related("customer"), pk=pk, source=Loan.APP)
    if loan.customer.user_id != request.user.id:
        messages.error(request, "You can only view your own loans.")
        return redirect("loans:my_loans")
    return render(request, "loans/my_loan_detail.html", {
        "loan": loan,
        "payment_requests": loan.payment_requests.order_by("-requested_at"),
    })


@login_required
def request_payment(request, pk):
    loan = get_object_or_404(Loan.objects.select_related("customer"), pk=pk, source=Loan.APP)
    if loan.customer.user_id != request.user.id:
        messages.error(request, "You can only pay off your own loans.")
        return redirect("loans:my_loans")
    if loan.status == Loan.PAID:
        messages.info(request, "This loan is already fully paid.")
        return redirect("loans:my_loan_detail", pk=loan.pk)
    if loan.payment_requests.filter(status=LoanPaymentRequest.PENDING).exists():
        messages.info(request, "You already have a payment request pending review for this loan.")
        return redirect("loans:my_loan_detail", pk=loan.pk)

    form = LoanPaymentRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        LoanPaymentRequest.objects.create(
            loan=loan,
            user=request.user,
            amount=form.cleaned_data["amount"],
            method=form.cleaned_data["method"],
            reference=form.cleaned_data.get("reference", ""),
            notes=form.cleaned_data.get("notes", ""),
        )
        messages.success(request, "Payment request submitted. We'll confirm once we've received it.")
        return redirect("loans:my_loan_detail", pk=loan.pk)

    return render(request, "loans/request_payment.html", {"loan": loan, "form": form})


# --------------------------------------------------------------------------- #
#  staff: approval queue for Quick Loan requests + payment claims              #
# --------------------------------------------------------------------------- #
@loan_admin_required
def request_queue(request):
    return render(request, "loans/request_queue.html", {
        "section": "requests",
        "can_manage": True,
        "loan_requests": LoanRequest.objects.filter(status=LoanRequest.PENDING)
            .select_related("customer", "user"),
        "payment_requests": LoanPaymentRequest.objects.filter(status=LoanPaymentRequest.PENDING)
            .select_related("loan__customer", "user"),
    })


@loan_admin_required
@require_POST
def approve_loan_request(request, pk):
    req = get_object_or_404(LoanRequest, pk=pk, status=LoanRequest.PENDING)
    loan = req.approve(request.user)
    messages.success(
        request,
        f"Approved. {loan.reference} created for {req.customer.full_name} — "
        f"deposit K{req.amount} to {req.payout_number}.",
    )
    return redirect("loans:request_queue")


@loan_admin_required
@require_POST
def decline_loan_request(request, pk):
    req = get_object_or_404(LoanRequest, pk=pk, status=LoanRequest.PENDING)
    req.decline(request.user, request.POST.get("reason", ""))
    messages.success(request, "Loan request declined.")
    return redirect("loans:request_queue")


@loan_admin_required
@require_POST
def approve_payment_request(request, pk):
    req = get_object_or_404(LoanPaymentRequest, pk=pk, status=LoanPaymentRequest.PENDING)
    payment = req.approve(request.user)
    messages.success(request, f"Payment confirmed. Receipt {payment.receipt_number}.")
    return redirect("loans:request_queue")


@loan_admin_required
@require_POST
def decline_payment_request(request, pk):
    req = get_object_or_404(LoanPaymentRequest, pk=pk, status=LoanPaymentRequest.PENDING)
    req.decline(request.user, request.POST.get("reason", ""))
    messages.success(request, "Payment request declined.")
    return redirect("loans:request_queue")
