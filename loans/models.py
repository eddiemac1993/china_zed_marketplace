"""Data model for the in-house micro-loan book.

Money model
-----------
A loan has a *principal* (grows with top-ups) and a flat *interest_rate* (%).
    interest_amount  = principal * rate / 100
    total_repayment  = principal + interest_amount

Payments are allocated proportionally between principal and interest so that
partial payments always carry their share of profit:
    interest_part(payment)  = payment * interest_amount / total_repayment
That keeps "interest earned" and "profit" reporting stable without having to
replay the payment ledger in order.
"""
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils import timezone

from .utils import money

USER = settings.AUTH_USER_MODEL

# Loans get a grace period on top of the agreed term: the due date is the end of
# the period plus this many days.
DUE_DATE_GRACE_DAYS = 5


class LoanSettings(models.Model):
    """Single row of tunable business rules (pk is forced to 1)."""

    business_name = models.CharField(max_length=120, default="ChinaZed Loans")
    total_capital = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    interest_1_week = models.DecimalField(max_digits=5, decimal_places=2, default=20)
    interest_2_weeks = models.DecimalField(max_digits=5, decimal_places=2, default=30)
    interest_3_weeks = models.DecimalField(max_digits=5, decimal_places=2, default=35)
    interest_4_weeks = models.DecimalField(max_digits=5, decimal_places=2, default=45)

    remind_3_days_before = models.BooleanField(default=True)
    remind_1_day_before = models.BooleanField(default=True)
    remind_on_due_date = models.BooleanField(default=True)
    remind_when_overdue = models.BooleanField(default=True)

    sms_enabled = models.BooleanField(default=False)
    whatsapp_enabled = models.BooleanField(default=False)
    reminder_signature = models.CharField(
        max_length=120, default="ChinaZed Loans", blank=True
    )

    # -- self-service "app" loans: logged-in customers request, staff approve --
    app_loans_enabled = models.BooleanField(
        default=True, help_text="Turn the in-app Quick Loan feature on or off."
    )
    app_loan_min_amount = models.DecimalField(max_digits=10, decimal_places=2, default=10)
    app_loan_starting_limit = models.DecimalField(
        max_digits=10, decimal_places=2, default=10,
        help_text="Maximum a first-time borrower can request.",
    )
    app_loan_growth_multiplier = models.DecimalField(
        max_digits=4, decimal_places=2, default=Decimal("1.50"),
        help_text="Next limit = last repaid loan's amount x this, once they pay it off.",
    )
    app_loan_max_limit = models.DecimalField(max_digits=12, decimal_places=2, default=2000)

    app_interest_1_week = models.DecimalField(max_digits=5, decimal_places=2, default=5)
    app_interest_2_weeks = models.DecimalField(max_digits=5, decimal_places=2, default=8)
    app_interest_3_weeks = models.DecimalField(max_digits=5, decimal_places=2, default=12)
    app_interest_4_weeks = models.DecimalField(max_digits=5, decimal_places=2, default=15)

    auto_blacklist_enabled = models.BooleanField(
        default=True,
        help_text="Automatically blacklist a customer once a loan is this overdue.",
    )
    auto_blacklist_overdue_days = models.PositiveSmallIntegerField(
        default=30,
        help_text="Days past due before a customer is auto-blacklisted.",
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Loan settings"
        verbose_name_plural = "Loan settings"

    def __str__(self):
        return self.business_name

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> "LoanSettings":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def rate_for_period(self, weeks: int) -> Decimal:
        return {
            1: self.interest_1_week,
            2: self.interest_2_weeks,
            3: self.interest_3_weeks,
            4: self.interest_4_weeks,
        }.get(int(weeks), self.interest_4_weeks)

    def app_rate_for_period(self, weeks: int) -> Decimal:
        return {
            1: self.app_interest_1_week,
            2: self.app_interest_2_weeks,
            3: self.app_interest_3_weeks,
            4: self.app_interest_4_weeks,
        }.get(int(weeks), self.app_interest_4_weeks)


class LoanCustomer(models.Model):
    GOOD = "good"
    LATE = "late"
    BLACKLISTED = "blacklisted"
    STATUS_CHOICES = [
        (GOOD, "Good customer"),
        (LATE, "Late"),
        (BLACKLISTED, "Blacklisted"),
    ]

    user = models.OneToOneField(
        USER, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="loan_customer",
        help_text="Linked site account, for customers who apply in-app.",
    )
    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30, blank=True)
    nrc_number = models.CharField(
        "NRC number", max_length=30, blank=True, null=True, unique=True
    )
    employer = models.CharField(max_length=150, blank=True)
    department = models.CharField(max_length=120, blank=True)
    employee_number = models.CharField(max_length=60, blank=True)
    salary_date = models.CharField(
        max_length=40, blank=True, help_text="e.g. 28th, or 'last working day'"
    )
    next_of_kin = models.CharField(max_length=150, blank=True)
    next_of_kin_phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    profile_picture = models.ImageField(
        upload_to="loans/customers/", blank=True, null=True
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=GOOD)
    notes = models.TextField(blank=True)

    created_by = models.ForeignKey(
        USER, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="loan_customers_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["full_name"]

    def __str__(self):
        return self.full_name

    def save(self, *args, **kwargs):
        # keep blank NRCs as NULL so the unique constraint allows many of them
        self.nrc_number = (self.nrc_number or "").strip() or None
        super().save(*args, **kwargs)

    # -- aggregates used across the dashboard and the customer timeline --
    @property
    def open_loans(self):
        return self.loans.exclude(status=Loan.PAID)

    @property
    def total_borrowed(self) -> Decimal:
        return money(self.loans.aggregate(t=Sum("principal"))["t"] or 0)

    @property
    def total_repaid(self) -> Decimal:
        total = LoanPayment.objects.filter(loan__customer=self).aggregate(
            t=Sum("amount_paid")
        )["t"]
        return money(total or 0)

    @property
    def total_outstanding(self) -> Decimal:
        return money(sum((loan.balance for loan in self.open_loans), Decimal("0")))

    @property
    def profit_generated(self) -> Decimal:
        return money(sum((loan.interest_collected for loan in self.loans.all()), Decimal("0")))

    @property
    def late_payment_count(self) -> int:
        return LoanPayment.objects.filter(
            loan__customer=self, paid_late=True
        ).count()

    def recalc_status(self, *, save=True):
        """Nudge the customer label from their repayment behaviour.

        Blacklisting here is automatic and reversible only by a human: once a
        staff member sets the status away from Blacklisted, it will only be
        set back if a loan is (still, or again) overdue past the threshold.
        """
        if self.status == self.BLACKLISTED:
            return

        cfg = LoanSettings.load()
        severely_overdue = False
        if cfg.auto_blacklist_enabled:
            severely_overdue = any(
                loan.status == Loan.OVERDUE
                and -loan.days_until_due >= cfg.auto_blacklist_overdue_days
                for loan in self.open_loans
            )

        if severely_overdue:
            new_status = self.BLACKLISTED
        elif self.open_loans.filter(status=Loan.OVERDUE).exists() or self.late_payment_count:
            new_status = self.LATE
        else:
            new_status = self.GOOD
        if new_status != self.status:
            self.status = new_status
            if save:
                self.save(update_fields=["status", "updated_at"])


class Loan(models.Model):
    ACTIVE = "active"
    DUE_SOON = "due_soon"
    OVERDUE = "overdue"
    PAID = "paid"
    STATUS_CHOICES = [
        (ACTIVE, "Active"),
        (DUE_SOON, "Due soon"),
        (OVERDUE, "Overdue"),
        (PAID, "Paid"),
    ]
    STATUS_META = {
        ACTIVE: {"label": "Active", "dot": "🟢", "css": "green"},
        DUE_SOON: {"label": "Due soon", "dot": "🟡", "css": "amber"},
        OVERDUE: {"label": "Overdue", "dot": "🔴", "css": "red"},
        PAID: {"label": "Paid", "dot": "⚪", "css": "grey"},
    }

    PERIOD_CHOICES = [
        (1, "1 Week"),
        (2, "2 Weeks"),
        (3, "3 Weeks"),
        (4, "4 Weeks"),
    ]

    CASH = "cash"
    MOBILE_MONEY = "mobile_money"
    BANK = "bank"
    OTHER = "other"
    METHOD_CHOICES = [
        (CASH, "Cash"),
        (MOBILE_MONEY, "Mobile money"),
        (BANK, "Bank transfer"),
        (OTHER, "Other"),
    ]

    MANUAL = "manual"
    APP = "app"
    SOURCE_CHOICES = [(MANUAL, "Manual (staff)"), (APP, "App (self-service)")]

    reference = models.CharField(max_length=20, unique=True, editable=False)
    customer = models.ForeignKey(
        LoanCustomer, on_delete=models.CASCADE, related_name="loans"
    )
    source = models.CharField(max_length=10, choices=SOURCE_CHOICES, default=MANUAL)

    original_principal = models.DecimalField(max_digits=12, decimal_places=2)
    principal = models.DecimalField(
        max_digits=12, decimal_places=2,
        help_text="Original principal plus every top-up.",
    )
    interest_rate = models.DecimalField(
        max_digits=5, decimal_places=2, help_text="Flat interest for the whole period, %."
    )
    period_weeks = models.PositiveSmallIntegerField(choices=PERIOD_CHOICES, default=4)

    issue_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(blank=True)
    payment_method = models.CharField(
        max_length=20, choices=METHOD_CHOICES, default=CASH
    )
    notes = models.TextField(blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=ACTIVE)
    paid_date = models.DateField(null=True, blank=True)
    paid_by = models.CharField(max_length=120, blank=True)
    receipt_number = models.CharField(max_length=20, blank=True)

    created_by = models.ForeignKey(
        USER, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="loans_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-issue_date", "-id"]

    def __str__(self):
        return f"{self.reference} · {self.customer.full_name}"

    # ---------------------------------------------------------------- money
    @property
    def interest_amount(self) -> Decimal:
        return money(self.principal * self.interest_rate / Decimal("100"))

    @property
    def total_repayment(self) -> Decimal:
        return money(self.principal + self.interest_amount)

    @property
    def amount_paid(self) -> Decimal:
        return money(self.payments.aggregate(t=Sum("amount_paid"))["t"] or 0)

    @property
    def balance(self) -> Decimal:
        return money(max(Decimal("0"), self.total_repayment - self.amount_paid))

    @property
    def outstanding_amount(self) -> Decimal:
        return self.balance

    @property
    def interest_ratio(self) -> Decimal:
        if self.total_repayment <= 0:
            return Decimal("0")
        return self.interest_amount / self.total_repayment

    @property
    def interest_collected(self) -> Decimal:
        return money(self.amount_paid * self.interest_ratio)

    @property
    def remaining_interest(self) -> Decimal:
        return money(max(Decimal("0"), self.interest_amount - self.interest_collected))

    @property
    def is_fully_paid(self) -> bool:
        return self.balance <= 0

    @property
    def days_until_due(self) -> int:
        return (self.due_date - timezone.localdate()).days

    @property
    def is_overdue(self) -> bool:
        return not self.is_fully_paid and timezone.localdate() > self.due_date

    @property
    def status_meta(self) -> dict:
        return self.STATUS_META[self.status]

    # ---------------------------------------------------------------- behaviour
    def compute_due_date(self):
        return self.issue_date + timedelta(
            weeks=int(self.period_weeks), days=DUE_DATE_GRACE_DAYS
        )

    def _next_reference(self):
        last = Loan.objects.order_by("-id").first()
        nxt = (last.id + 1) if last else 1
        return f"LN-{nxt:05d}"

    def refresh_status(self, *, save=True):
        old = self.status
        if self.is_fully_paid:
            self.status = self.PAID
            if not self.paid_date:
                self.paid_date = timezone.localdate()
            if not self.receipt_number:
                self.receipt_number = f"LR-{self.id:05d}"
            last_payment = self.payments.order_by("-payment_date", "-id").first()
            if last_payment and not self.paid_by:
                self.paid_by = last_payment.officer
        else:
            # no longer fully paid (e.g. a payment or top-up was edited/removed) -
            # clear the paid-off markers so they don't linger from a past state
            self.paid_date = None
            self.receipt_number = ""
            self.paid_by = ""
            if timezone.localdate() > self.due_date:
                self.status = self.OVERDUE
            elif 0 <= self.days_until_due <= 3:
                self.status = self.DUE_SOON
            else:
                self.status = self.ACTIVE
        if save and (self.status != old or self.pk):
            self.save(update_fields=[
                "status", "paid_date", "paid_by", "receipt_number", "updated_at",
            ])
        self.customer.recalc_status()
        return self.status

    def resync_topup_snapshots(self):
        """Re-derive principal and every top-up's before/after snapshot from the
        current original principal + rate. Call after editing the base loan."""
        running = money(self.original_principal)
        for topup in self.topups.order_by("date", "id"):
            topup.principal_before = running
            running = money(running + topup.amount)
            topup.principal_after = running
            topup.repayment_after = money(
                running + running * self.interest_rate / Decimal("100")
            )
            topup.save(update_fields=[
                "principal_before", "principal_after", "repayment_after",
            ])
        self.principal = running
        self.save(update_fields=["principal", "updated_at"])

    def add_topup(self, *, amount, user, note="", date=None):
        amount = money(amount)
        topup = LoanTopUp.objects.create(
            loan=self,
            amount=amount,
            date=date or timezone.localdate(),
            principal_before=self.principal,
            principal_after=money(self.principal + amount),
            note=note,
            created_by=user,
        )
        self.principal = topup.principal_after
        self.save(update_fields=["principal", "updated_at"])
        topup.repayment_after = self.total_repayment
        topup.save(update_fields=["repayment_after"])
        self.refresh_status()
        return topup

    def save(self, *args, **kwargs):
        if not self.pk and not self.reference:
            self.reference = self._next_reference()
        if self.original_principal is None:
            self.original_principal = self.principal
        if self.principal is None:
            self.principal = self.original_principal
        if not self.due_date:
            self.due_date = self.compute_due_date()
        super().save(*args, **kwargs)


class LoanTopUp(models.Model):
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name="topups")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField(default=timezone.localdate)
    principal_before = models.DecimalField(max_digits=12, decimal_places=2)
    principal_after = models.DecimalField(max_digits=12, decimal_places=2)
    repayment_after = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    note = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        USER, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="loan_topups_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"Top-up {self.amount} on {self.loan.reference}"


class LoanPayment(models.Model):
    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name="payments")
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2)
    payment_date = models.DateField(default=timezone.localdate)
    method = models.CharField(
        max_length=20, choices=Loan.METHOD_CHOICES, default=Loan.CASH
    )
    reference = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)

    receipt_number = models.CharField(max_length=20, unique=True, editable=False)
    officer = models.CharField(max_length=120, blank=True)
    paid_late = models.BooleanField(default=False)

    balance_after = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )

    created_by = models.ForeignKey(
        USER, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="loan_payments_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-payment_date", "-id"]

    def __str__(self):
        return f"{self.receipt_number} · {self.amount_paid}"

    @property
    def interest_part(self) -> Decimal:
        return money(self.amount_paid * self.loan.interest_ratio)

    @property
    def principal_part(self) -> Decimal:
        return money(self.amount_paid - self.interest_part)

    def _next_receipt(self):
        last = LoanPayment.objects.order_by("-id").first()
        nxt = (last.id + 1) if last else 1
        return f"RCP-{nxt:05d}"

    def save(self, *args, **kwargs):
        creating = self.pk is None
        if not self.receipt_number:
            self.receipt_number = self._next_receipt()
        if creating and self.payment_date and self.loan_id:
            self.paid_late = self.payment_date > self.loan.due_date
        super().save(*args, **kwargs)
        # keep the loan snapshot + status in step with the ledger
        self.balance_after = self.loan.balance
        super().save(update_fields=["balance_after"])
        self.loan.refresh_status()


class LoanReminderLog(models.Model):
    THREE_DAYS = "3_days_before"
    ONE_DAY = "1_day_before"
    ON_DUE = "on_due"
    OVERDUE = "overdue"
    KIND_CHOICES = [
        (THREE_DAYS, "3 days before due"),
        (ONE_DAY, "1 day before due"),
        (ON_DUE, "On due date"),
        (OVERDUE, "After overdue"),
    ]

    loan = models.ForeignKey(
        Loan, on_delete=models.CASCADE, related_name="reminders"
    )
    customer = models.ForeignKey(
        LoanCustomer, on_delete=models.CASCADE, related_name="reminders"
    )
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    channel = models.CharField(max_length=20, default="log")
    message = models.TextField(blank=True)
    success = models.BooleanField(default=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-sent_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["loan", "kind"], name="loans_one_reminder_per_kind"
            )
        ]

    def __str__(self):
        return f"{self.get_kind_display()} → {self.customer.full_name}"


class LoanRequest(models.Model):
    """A logged-in customer asking for a new Quick Loan. Approving it means the
    money has been deposited to their number; declining leaves nothing behind."""

    PENDING = "pending"
    APPROVED = "approved"
    DECLINED = "declined"
    STATUS_CHOICES = [
        (PENDING, "Pending review"),
        (APPROVED, "Approved · deposited"),
        (DECLINED, "Declined"),
    ]

    user = models.ForeignKey(USER, on_delete=models.CASCADE, related_name="loan_requests")
    customer = models.ForeignKey(
        LoanCustomer, on_delete=models.CASCADE, related_name="loan_requests"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    period_weeks = models.PositiveSmallIntegerField(choices=Loan.PERIOD_CHOICES)
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2)
    payout_number = models.CharField(
        max_length=30, help_text="Mobile money number to deposit to (from their profile)."
    )
    notes = models.CharField(max_length=255, blank=True)

    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=PENDING)
    decision_notes = models.CharField(max_length=255, blank=True)
    loan = models.OneToOneField(
        Loan, null=True, blank=True, on_delete=models.SET_NULL, related_name="app_request"
    )

    requested_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        USER, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="loan_requests_decided",
    )

    class Meta:
        ordering = ["-requested_at"]

    def __str__(self):
        return f"K{self.amount} request · {self.customer.full_name} ({self.get_status_display()})"

    @property
    def interest_amount(self) -> Decimal:
        return money(self.amount * self.interest_rate / Decimal("100"))

    @property
    def total_repayment(self) -> Decimal:
        return money(self.amount + self.interest_amount)

    def approve(self, staff_user):
        if self.status != self.PENDING:
            raise ValueError("This request was already decided.")
        loan = Loan.objects.create(
            customer=self.customer,
            original_principal=self.amount,
            principal=self.amount,
            interest_rate=self.interest_rate,
            period_weeks=self.period_weeks,
            issue_date=timezone.localdate(),
            payment_method=Loan.MOBILE_MONEY,
            source=Loan.APP,
            notes=f"App loan request #{self.pk} — deposited to {self.payout_number}.",
            created_by=staff_user,
        )
        loan.refresh_status()
        self.loan = loan
        self.status = self.APPROVED
        self.decided_at = timezone.now()
        self.decided_by = staff_user
        self.save(update_fields=["loan", "status", "decided_at", "decided_by"])
        return loan

    def decline(self, staff_user, reason=""):
        if self.status != self.PENDING:
            raise ValueError("This request was already decided.")
        self.status = self.DECLINED
        self.decision_notes = reason
        self.decided_at = timezone.now()
        self.decided_by = staff_user
        self.save(update_fields=["status", "decision_notes", "decided_at", "decided_by"])


class LoanPaymentRequest(models.Model):
    """A customer telling us they sent money towards a loan. Approving it is
    what actually records the LoanPayment — i.e. confirms we received it."""

    PENDING = "pending"
    APPROVED = "approved"
    DECLINED = "declined"
    STATUS_CHOICES = [
        (PENDING, "Pending review"),
        (APPROVED, "Approved · received"),
        (DECLINED, "Declined"),
    ]

    loan = models.ForeignKey(Loan, on_delete=models.CASCADE, related_name="payment_requests")
    user = models.ForeignKey(
        USER, on_delete=models.CASCADE, related_name="loan_payment_requests"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(
        max_length=20, choices=Loan.METHOD_CHOICES, default=Loan.MOBILE_MONEY
    )
    reference = models.CharField(max_length=120, blank=True)
    notes = models.CharField(max_length=255, blank=True)

    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=PENDING)
    decision_notes = models.CharField(max_length=255, blank=True)
    payment = models.OneToOneField(
        LoanPayment, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="app_request",
    )

    requested_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(
        USER, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="loan_payment_requests_decided",
    )

    class Meta:
        ordering = ["-requested_at"]

    def __str__(self):
        return f"K{self.amount} payment · {self.loan.reference} ({self.get_status_display()})"

    def approve(self, staff_user):
        if self.status != self.PENDING:
            raise ValueError("This request was already decided.")
        payment = LoanPayment.objects.create(
            loan=self.loan,
            amount_paid=self.amount,
            payment_date=timezone.localdate(),
            method=self.method,
            reference=self.reference,
            notes=f"Customer payment request #{self.pk}. {self.notes}".strip(),
            officer=staff_user.get_full_name() or staff_user.get_username(),
            created_by=staff_user,
        )
        self.payment = payment
        self.status = self.APPROVED
        self.decided_at = timezone.now()
        self.decided_by = staff_user
        self.save(update_fields=["payment", "status", "decided_at", "decided_by"])
        return payment

    def decline(self, staff_user, reason=""):
        if self.status != self.PENDING:
            raise ValueError("This request was already decided.")
        self.status = self.DECLINED
        self.decision_notes = reason
        self.decided_at = timezone.now()
        self.decided_by = staff_user
        self.save(update_fields=["status", "decision_notes", "decided_at", "decided_by"])
