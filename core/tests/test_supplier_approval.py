from types import SimpleNamespace
from unittest.mock import patch
import base64
import tempfile

from allauth.account.signals import user_signed_up
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

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


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(), SECURE_SSL_REDIRECT=False)
class StaffQuickPublishTests(TestCase):
    def test_staff_can_complete_and_publish_draft_from_profile(self):
        staff = get_user_model().objects.create_user("admin", password="pass", is_staff=True)
        category = Category.objects.create(name="Shoes")
        product = Product.objects.create(
            name="Draft shoe",
            description="Draft",
            rmb_price="0.00",
            status="draft",
            is_available=False,
        )
        image = SimpleUploadedFile(
            "shoe.png",
            base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="),
            content_type="image/png",
        )
        self.client.force_login(staff)

        response = self.client.post(
            reverse("staff_quick_publish_product", args=[product.pk]),
            {
                "product-%s-name" % product.pk: "Ready shoe",
                "product-%s-category" % product.pk: category.pk,
                "product-%s-description" % product.pk: "Customer-ready shoe",
                "product-%s-product_type" % product.pk: "preorder",
                "product-%s-rmb_price" % product.pk: "100.00",
                "product-%s-stock_quantity" % product.pk: "0",
                "product-%s-customer_image" % product.pk: image,
            },
        )

        self.assertRedirects(response, reverse("profile"))
        product.refresh_from_db()
        self.assertEqual(product.status, "active")
        self.assertTrue(product.is_available)
        self.assertTrue(product.gallery_images.filter(visibility="public", is_primary=True).exists())

    def test_invalid_quick_publish_returns_to_open_profile_draft(self):
        staff = get_user_model().objects.create_user("admin", password="pass", is_staff=True)
        product = Product.objects.create(
            name="Draft shoe",
            description="Draft",
            rmb_price="100.00",
            status="draft",
            is_available=False,
        )
        self.client.force_login(staff)

        response = self.client.post(
            reverse("staff_quick_publish_product", args=[product.pk]),
            {
                "product-%s-name" % product.pk: "Draft shoe",
                "product-%s-description" % product.pk: "Draft",
                "product-%s-product_type" % product.pk: "preorder",
                "product-%s-rmb_price" % product.pk: "100.00",
                "product-%s-stock_quantity" % product.pk: "0",
            },
        )

        expected = f"{reverse('profile')}?edit_product={product.pk}#quick-product-{product.pk}"
        self.assertRedirects(response, expected, fetch_redirect_response=False)
        product.refresh_from_db()
        self.assertEqual(product.status, "draft")
