from decimal import Decimal

from django import forms
from django.utils import timezone

from .models import (
    DUE_DATE_GRACE_DAYS,
    Loan,
    LoanCustomer,
    LoanPayment,
    LoanSettings,
    LoanTopUp,
)

_INPUT = (
    "w-full rounded-lg border border-slate-300 px-3 py-2 text-sm "
    "focus:border-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-200"
)


def _style(fields):
    for field in fields.values():
        widget = field.widget
        base = _INPUT
        if isinstance(widget, forms.CheckboxInput):
            base = "h-4 w-4 rounded border-slate-300 text-indigo-600"
        elif isinstance(widget, (forms.Select, forms.SelectMultiple)):
            base = _INPUT + " bg-white"
        widget.attrs.setdefault("class", base)
        if isinstance(widget, forms.DateInput):
            widget.input_type = "date"


class LoanCustomerForm(forms.ModelForm):
    class Meta:
        model = LoanCustomer
        fields = [
            "full_name", "phone", "nrc_number", "employer", "department",
            "employee_number", "salary_date", "next_of_kin", "next_of_kin_phone",
            "address", "profile_picture", "status", "notes",
        ]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 2}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self.fields)
        self.fields["nrc_number"].required = False
        self.fields["phone"].required = False

    def clean_nrc_number(self):
        return (self.cleaned_data.get("nrc_number") or "").strip() or None


class LoanForm(forms.ModelForm):
    class Meta:
        model = Loan
        fields = [
            "customer", "original_principal", "interest_rate", "period_weeks",
            "issue_date", "due_date", "payment_method", "notes",
        ]
        widgets = {
            "issue_date": forms.DateInput(),
            "due_date": forms.DateInput(),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }
        labels = {"original_principal": "Loan amount", "interest_rate": "Interest %"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self.fields)
        self.fields["due_date"].required = False
        self.fields["due_date"].help_text = (
            f"Leave blank to auto-calculate: end of the period + "
            f"{DUE_DATE_GRACE_DAYS} days grace."
        )
        qs = LoanCustomer.objects.exclude(status=LoanCustomer.BLACKLISTED)
        if self.instance.pk:
            qs = qs | LoanCustomer.objects.filter(pk=self.instance.customer_id)
        self.fields["customer"].queryset = qs.distinct()
        if not self.instance.pk:
            self.fields["issue_date"].initial = timezone.localdate()
        elif self.instance.topups.exists():
            self.fields["original_principal"].help_text = (
                f"Original advance only. This loan also has "
                f"K{self.instance.principal - self.instance.original_principal} in top-ups."
            )

    def clean(self):
        cleaned = super().clean()
        issue = cleaned.get("issue_date")
        weeks = cleaned.get("period_weeks")
        due = cleaned.get("due_date")
        if issue and weeks and not due:
            cleaned["due_date"] = issue + timezone.timedelta(
                weeks=int(weeks), days=DUE_DATE_GRACE_DAYS
            )
        if cleaned.get("due_date") and issue and cleaned["due_date"] < issue:
            self.add_error("due_date", "Due date cannot be before the issue date.")
        return cleaned

    def save(self, commit=True):
        loan = super().save(commit=False)
        topups = Decimal("0")
        if loan.pk:
            topups = sum(
                (t.amount for t in loan.topups.all()), Decimal("0")
            )
        loan.principal = loan.original_principal + topups
        if commit:
            loan.save()
        return loan


class LoanTopUpForm(forms.ModelForm):
    class Meta:
        model = LoanTopUp
        fields = ["amount", "date", "note"]
        widgets = {"date": forms.DateInput()}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self.fields)
        self.fields["date"].initial = timezone.localdate()

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError("Top-up amount must be positive.")
        return amount


class LoanPaymentForm(forms.ModelForm):
    class Meta:
        model = LoanPayment
        fields = ["amount_paid", "payment_date", "method", "reference", "notes"]
        widgets = {
            "payment_date": forms.DateInput(),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, loan=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.loan = loan
        _style(self.fields)
        self.fields["payment_date"].initial = timezone.localdate()

    def clean_amount_paid(self):
        amount = self.cleaned_data["amount_paid"]
        if amount <= 0:
            raise forms.ValidationError("Payment amount must be positive.")
        if self.loan and amount - self.loan.balance > 1:
            raise forms.ValidationError(
                f"That is more than the outstanding balance (K{self.loan.balance})."
            )
        return amount


class LoanSettingsForm(forms.ModelForm):
    class Meta:
        model = LoanSettings
        fields = [
            "business_name", "total_capital",
            "interest_1_week", "interest_2_weeks", "interest_3_weeks", "interest_4_weeks",
            "remind_3_days_before", "remind_1_day_before", "remind_on_due_date",
            "remind_when_overdue", "sms_enabled", "whatsapp_enabled",
            "reminder_signature",
            "app_loans_enabled", "app_loan_min_amount", "app_loan_starting_limit",
            "app_loan_growth_multiplier", "app_loan_max_limit",
            "app_interest_1_week", "app_interest_2_weeks",
            "app_interest_3_weeks", "app_interest_4_weeks",
            "auto_blacklist_enabled", "auto_blacklist_overdue_days",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self.fields)


# --------------------------------------------------------------------------- #
#  customer-facing (Quick Loan) forms                                          #
# --------------------------------------------------------------------------- #
class LoanApplicationForm(forms.Form):
    amount = forms.DecimalField(max_digits=12, decimal_places=2, label="How much do you need?")
    period_weeks = forms.ChoiceField(choices=Loan.PERIOD_CHOICES, label="Repay in")
    notes = forms.CharField(
        required=False, label="Anything we should know? (optional)",
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def __init__(self, *args, min_amount=None, max_amount=None, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self.fields)
        self.fields["period_weeks"].initial = Loan.PERIOD_CHOICES[0][0]
        self.min_amount = min_amount
        self.max_amount = max_amount

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError("Enter an amount greater than zero.")
        if self.min_amount is not None and amount < self.min_amount:
            raise forms.ValidationError(f"The minimum you can request is K{self.min_amount}.")
        if self.max_amount is not None and amount > self.max_amount:
            raise forms.ValidationError(
                f"You're eligible for up to K{self.max_amount} right now. "
                f"Repay a loan on time to unlock a higher limit."
            )
        return amount


class LoanPaymentRequestForm(forms.Form):
    amount = forms.DecimalField(max_digits=12, decimal_places=2, label="Amount you sent")
    method = forms.ChoiceField(choices=Loan.METHOD_CHOICES, label="How did you pay?")
    reference = forms.CharField(
        max_length=120, required=False, label="Transaction reference (optional)",
        help_text="Mobile money transaction ID, if you have one.",
    )
    notes = forms.CharField(
        required=False, label="Notes (optional)", widget=forms.Textarea(attrs={"rows": 2})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style(self.fields)
        self.fields["method"].initial = Loan.MOBILE_MONEY

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if amount <= 0:
            raise forms.ValidationError("Enter an amount greater than zero.")
        return amount
