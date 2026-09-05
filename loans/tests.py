from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import Group, User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.models import CustomerProfile

from .eligibility import blocking_reason, eligible_limit, get_or_create_customer
from .models import (
    Loan,
    LoanCustomer,
    LoanPayment,
    LoanPaymentRequest,
    LoanReminderLog,
    LoanRequest,
    LoanSettings,
)
from .reminders import run_reminders
from .utils import LOAN_ADMIN_GROUP


class LoanMathTests(TestCase):
    def setUp(self):
        self.customer = LoanCustomer.objects.create(
            full_name="Mary Banda", phone="0970000000", nrc_number="111111/11/1"
        )

    def make_loan(self, principal="500", rate="35", weeks=3, issue=None):
        issue = issue or timezone.localdate()
        loan = Loan(
            customer=self.customer,
            original_principal=Decimal(principal),
            principal=Decimal(principal),
            interest_rate=Decimal(rate),
            period_weeks=weeks,
            issue_date=issue,
        )
        loan.save()
        return loan

    def test_interest_and_repayment(self):
        loan = self.make_loan("500", "35")
        self.assertEqual(loan.interest_amount, Decimal("175.00"))
        self.assertEqual(loan.total_repayment, Decimal("675.00"))

    def test_due_date_auto_from_period_plus_grace(self):
        issue = timezone.localdate()
        loan = self.make_loan(weeks=2, issue=issue)
        self.assertEqual(loan.due_date, issue + timedelta(weeks=2, days=5))

    def test_reference_is_sequential(self):
        a = self.make_loan()
        b = self.make_loan()
        self.assertNotEqual(a.reference, b.reference)
        self.assertTrue(a.reference.startswith("LN-"))

    def test_topup_grows_principal_and_keeps_history(self):
        loan = self.make_loan("600", "35")
        loan.add_topup(amount=Decimal("500"), user=None, note="second advance")
        loan.refresh_from_db()
        self.assertEqual(loan.principal, Decimal("1100.00"))
        self.assertEqual(loan.total_repayment, Decimal("1485.00"))
        self.assertEqual(loan.topups.count(), 1)
        topup = loan.topups.first()
        self.assertEqual(topup.principal_before, Decimal("600.00"))
        self.assertEqual(topup.principal_after, Decimal("1100.00"))

    def test_partial_then_full_payment_marks_paid(self):
        loan = self.make_loan("500", "35")
        LoanPayment.objects.create(loan=loan, amount_paid=Decimal("200"))
        loan.refresh_from_db()
        self.assertNotEqual(loan.status, Loan.PAID)
        self.assertEqual(loan.balance, Decimal("475.00"))

        LoanPayment.objects.create(loan=loan, amount_paid=Decimal("475"))
        loan.refresh_from_db()
        self.assertEqual(loan.status, Loan.PAID)
        self.assertEqual(loan.balance, Decimal("0.00"))
        self.assertTrue(loan.receipt_number)
        self.assertIsNotNone(loan.paid_date)

    def test_overdue_status_and_customer_label(self):
        old_issue = timezone.localdate() - timedelta(days=40)
        loan = self.make_loan("500", "35", weeks=2, issue=old_issue)
        loan.refresh_status()
        self.assertEqual(loan.status, Loan.OVERDUE)
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.status, LoanCustomer.LATE)

    def test_interest_earned_tracks_collections(self):
        loan = self.make_loan("500", "35")
        LoanPayment.objects.create(loan=loan, amount_paid=Decimal("675"))
        loan.refresh_from_db()
        self.assertEqual(loan.interest_collected, Decimal("175.00"))


class ReminderTests(TestCase):
    def test_reminder_sent_once_per_kind(self):
        cfg = LoanSettings.load()
        cfg.remind_3_days_before = True
        cfg.save()
        customer = LoanCustomer.objects.create(
            full_name="John Phiri", phone="0966000000", nrc_number="222222/22/2"
        )
        # due = issue + 1 week + 5 days grace; want that 3 days from now
        issue = timezone.localdate() + timedelta(days=3) - timedelta(weeks=1, days=5)
        Loan.objects.create(
            customer=customer,
            original_principal=Decimal("400"), principal=Decimal("400"),
            interest_rate=Decimal("20"), period_weeks=1, issue_date=issue,
        )
        first = run_reminders()
        self.assertEqual(len(first), 1)
        self.assertEqual(LoanReminderLog.objects.count(), 1)
        second = run_reminders()
        self.assertEqual(len(second), 0)


class AccessControlTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user("staff", password="pw", is_staff=True)
        self.admin = User.objects.create_user("boss", password="pw", is_staff=True)
        self.admin.groups.add(Group.objects.create(name=LOAN_ADMIN_GROUP))
        self.shopper = User.objects.create_user("shopper", password="pw")

    def test_shopper_cannot_open_dashboard(self):
        self.client.force_login(self.shopper)
        resp = self.client.get(reverse("loans:dashboard"))
        self.assertEqual(resp.status_code, 302)

    def test_staff_can_view_but_not_create(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("loans:dashboard")).status_code, 200)
        resp = self.client.get(reverse("loans:loan_create"))
        self.assertRedirects(resp, reverse("loans:dashboard"))

    def test_admin_can_open_create(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("loans:loan_create")).status_code, 200)


class QuickLoanEligibilityTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("buyer", password="pw")
        CustomerProfile.objects.create(user=self.user, phone="0971111111")

    def test_first_time_limit_is_starting_limit(self):
        self.assertEqual(eligible_limit(self.user), LoanSettings.load().app_loan_starting_limit)

    def test_no_history_no_blocking_reason(self):
        self.assertEqual(blocking_reason(self.user), "")

    def test_limit_grows_after_full_repayment(self):
        customer = get_or_create_customer(self.user)
        loan = Loan.objects.create(
            customer=customer, original_principal=Decimal("100"), principal=Decimal("100"),
            interest_rate=Decimal("5"), period_weeks=1, issue_date=timezone.localdate(),
            source=Loan.APP,
        )
        LoanPayment.objects.create(loan=loan, amount_paid=loan.total_repayment)
        loan.refresh_from_db()
        self.assertEqual(loan.status, Loan.PAID)
        cfg = LoanSettings.load()
        expected = min(cfg.app_loan_max_limit, Decimal("100") * cfg.app_loan_growth_multiplier)
        self.assertEqual(eligible_limit(self.user), expected)

    def test_open_loan_blocks_new_request(self):
        customer = get_or_create_customer(self.user)
        Loan.objects.create(
            customer=customer, original_principal=Decimal("50"), principal=Decimal("50"),
            interest_rate=Decimal("5"), period_weeks=1, issue_date=timezone.localdate(),
            source=Loan.APP,
        )
        self.assertIn("active loan", blocking_reason(self.user))


class QuickLoanFlowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("buyer2", password="pw", email="buyer2@example.com")
        CustomerProfile.objects.create(user=self.user, phone="0972222222")
        self.admin = User.objects.create_user("boss2", password="pw", is_staff=True)
        self.admin.groups.add(Group.objects.create(name=LOAN_ADMIN_GROUP))

    def test_apply_requires_login(self):
        resp = self.client.get(reverse("loans:apply"))
        self.assertEqual(resp.status_code, 302)

    def test_apply_requires_profile_phone(self):
        bare = User.objects.create_user("nobody", password="pw")
        self.client.force_login(bare)
        resp = self.client.get(reverse("loans:apply"))
        self.assertRedirects(resp, reverse("profile") + "#customer-profile-form")

    def test_submit_request_then_admin_approval_creates_loan(self):
        self.client.force_login(self.user)
        resp = self.client.post(reverse("loans:apply"), {
            "amount": "10", "period_weeks": "1", "notes": "",
        })
        self.assertRedirects(resp, reverse("loans:my_loans"))
        req = LoanRequest.objects.get(user=self.user)
        self.assertEqual(req.status, LoanRequest.PENDING)
        self.assertEqual(req.payout_number, "0972222222")
        self.assertEqual(req.interest_rate, LoanSettings.load().app_interest_1_week)

        self.client.force_login(self.admin)
        resp = self.client.post(reverse("loans:approve_loan_request", args=[req.pk]))
        self.assertRedirects(resp, reverse("loans:request_queue"))
        req.refresh_from_db()
        self.assertEqual(req.status, LoanRequest.APPROVED)
        self.assertIsNotNone(req.loan)
        self.assertEqual(req.loan.source, Loan.APP)
        self.assertEqual(req.loan.principal, Decimal("10.00"))

    def test_over_limit_request_rejected(self):
        self.client.force_login(self.user)
        resp = self.client.post(reverse("loans:apply"), {
            "amount": "999999", "period_weeks": "1", "notes": "",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(LoanRequest.objects.filter(user=self.user).exists())

    def test_payment_request_then_approval_records_payment(self):
        customer = get_or_create_customer(self.user)
        loan = Loan.objects.create(
            customer=customer, original_principal=Decimal("100"), principal=Decimal("100"),
            interest_rate=Decimal("5"), period_weeks=1, issue_date=timezone.localdate(),
            source=Loan.APP,
        )
        self.client.force_login(self.user)
        resp = self.client.post(reverse("loans:request_payment", args=[loan.pk]), {
            "amount": "50", "method": "mobile_money", "reference": "TX123", "notes": "",
        })
        self.assertRedirects(resp, reverse("loans:my_loan_detail", args=[loan.pk]))
        preq = LoanPaymentRequest.objects.get(loan=loan)
        self.assertEqual(preq.status, LoanPaymentRequest.PENDING)

        self.client.force_login(self.admin)
        resp = self.client.post(reverse("loans:approve_payment_request", args=[preq.pk]))
        self.assertRedirects(resp, reverse("loans:request_queue"))
        loan.refresh_from_db()
        self.assertEqual(loan.amount_paid, Decimal("50.00"))
        preq.refresh_from_db()
        self.assertEqual(preq.status, LoanPaymentRequest.APPROVED)
        self.assertIsNotNone(preq.payment)

    def test_other_users_loan_is_not_visible(self):
        other = User.objects.create_user("stranger", password="pw")
        CustomerProfile.objects.create(user=other, phone="0970000099")
        customer = get_or_create_customer(other)
        loan = Loan.objects.create(
            customer=customer, original_principal=Decimal("20"), principal=Decimal("20"),
            interest_rate=Decimal("5"), period_weeks=1, issue_date=timezone.localdate(),
            source=Loan.APP,
        )
        self.client.force_login(self.user)
        resp = self.client.get(reverse("loans:my_loan_detail", args=[loan.pk]))
        self.assertRedirects(resp, reverse("loans:my_loans"))


class DeleteFeatureTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user("boss3", password="pw", is_staff=True)
        self.admin.groups.add(Group.objects.create(name=LOAN_ADMIN_GROUP))
        self.staff = User.objects.create_user("staff3", password="pw", is_staff=True)
        self.customer = LoanCustomer.objects.create(
            full_name="Delete Test", phone="0970000000", nrc_number="333333/33/3"
        )

    def make_loan(self, principal="500", rate="35", weeks=1):
        return Loan.objects.create(
            customer=self.customer,
            original_principal=Decimal(principal), principal=Decimal(principal),
            interest_rate=Decimal(rate), period_weeks=weeks, issue_date=timezone.localdate(),
        )

    def test_deleting_last_payment_reverts_paid_status(self):
        loan = self.make_loan("500", "35")
        payment = LoanPayment.objects.create(loan=loan, amount_paid=loan.total_repayment)
        loan.refresh_from_db()
        self.assertEqual(loan.status, Loan.PAID)
        self.assertIsNotNone(loan.paid_date)
        self.assertTrue(loan.receipt_number)

        self.client.force_login(self.admin)
        resp = self.client.post(reverse("loans:payment_delete", args=[payment.pk]))
        self.assertRedirects(resp, reverse("loans:loan_detail", args=[loan.pk]))
        loan.refresh_from_db()
        self.assertNotEqual(loan.status, Loan.PAID)
        self.assertIsNone(loan.paid_date)
        self.assertEqual(loan.receipt_number, "")
        self.assertEqual(loan.amount_paid, Decimal("0.00"))

    def test_deleting_topup_shrinks_principal_back(self):
        loan = self.make_loan("600", "15")
        topup = loan.add_topup(amount=Decimal("500"), user=self.admin)
        loan.refresh_from_db()
        self.assertEqual(loan.principal, Decimal("1100.00"))

        self.client.force_login(self.admin)
        resp = self.client.post(reverse("loans:topup_delete", args=[topup.pk]))
        self.assertRedirects(resp, reverse("loans:loan_detail", args=[loan.pk]))
        loan.refresh_from_db()
        self.assertEqual(loan.principal, Decimal("600.00"))
        self.assertEqual(loan.total_repayment, Decimal("690.00"))
        self.assertEqual(loan.topups.count(), 0)

    def test_customer_delete_blocked_when_loans_exist(self):
        self.make_loan()
        self.client.force_login(self.admin)
        resp = self.client.post(reverse("loans:customer_delete", args=[self.customer.pk]))
        self.assertRedirects(resp, reverse("loans:customer_detail", args=[self.customer.pk]))
        self.assertTrue(LoanCustomer.objects.filter(pk=self.customer.pk).exists())

    def test_customer_delete_allowed_with_no_loans(self):
        self.client.force_login(self.admin)
        resp = self.client.post(reverse("loans:customer_delete", args=[self.customer.pk]))
        self.assertRedirects(resp, reverse("loans:customer_list"))
        self.assertFalse(LoanCustomer.objects.filter(pk=self.customer.pk).exists())

    def test_non_admin_staff_cannot_delete(self):
        loan = self.make_loan()
        payment = LoanPayment.objects.create(loan=loan, amount_paid=Decimal("10"))
        self.client.force_login(self.staff)
        resp = self.client.post(reverse("loans:payment_delete", args=[payment.pk]))
        self.assertRedirects(resp, reverse("loans:dashboard"))
        self.assertTrue(LoanPayment.objects.filter(pk=payment.pk).exists())
