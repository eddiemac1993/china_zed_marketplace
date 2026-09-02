from types import SimpleNamespace
from unittest.mock import patch

from allauth.account.signals import user_signed_up
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings

from core.admin import approve_supplier_requests
from core.models import Category, Product, SupplierProductRequest


@override_settings(SITE_OWNER_EMAIL="owner@example.com")
class GoogleSignupNotificationTests(TestCase):
    @patch("core.signals.send_mail")
    def test_first_google_signup_notifies_owner(self, send_mail_mock):
        user = get_user_model().objects.create_user(
            username="google-customer",
            email="customer@example.com",
        )
        sociallogin = SimpleNamespace(account=SimpleNamespace(provider="google"))

        user_signed_up.send(
            sender=get_user_model(),
            request=RequestFactory().get("/"),
            user=user,
            sociallogin=sociallogin,
        )

        send_mail_mock.assert_called_once()
        self.assertEqual(send_mail_mock.call_args.kwargs["recipient_list"], ["owner@example.com"])


class SupplierApprovalTests(TestCase):
    @patch("core.admin.messages.success")
    def test_preapproved_unconverted_submission_still_creates_draft(self, _success):
        category = Category.objects.create(name="Footwear")
        submission = SupplierProductRequest.objects.create(
            supplier_name="Supplier",
            product_name="Walking shoe",
            description="Comfortable shoe",
            product_type="preorder",
            category=category,
            rmb_price="100.00",
            is_reviewed=True,
            is_approved=True,
        )

        approve_supplier_requests(
            None,
            RequestFactory().post("/admin/"),
            SupplierProductRequest.objects.filter(pk=submission.pk),
        )

        submission.refresh_from_db()
        self.assertIsNotNone(submission.converted_product_id)
        product = Product.objects.get(pk=submission.converted_product_id)
        self.assertEqual(product.status, "draft")
        self.assertFalse(product.is_available)
