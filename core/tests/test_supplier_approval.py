from types import SimpleNamespace
from unittest.mock import patch
import base64
import json
import os
import tempfile

from allauth.account.signals import user_signed_up
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from core.admin import approve_supplier_requests
from core.models import Category, Product, SupplierProductRequest, SupplierProductRequestImage


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

    def test_staff_can_publish_using_confirmed_existing_supplier_photo(self):
        staff = get_user_model().objects.create_user("photo-admin", password="pass", is_staff=True)
        category = Category.objects.create(name="Footwear")
        product = Product.objects.create(name="Draft", description="Draft", rmb_price="100", status="draft", is_available=False)
        submission = SupplierProductRequest.objects.create(
            submitted_by=staff, converted_product=product, supplier_name="Admin",
            product_name="Draft", description="Draft", category=category,
            rmb_price="100", is_reviewed=True, is_approved=True,
        )
        source_image = SupplierProductRequestImage.objects.create(
            supplier_request=submission,
            image=SimpleUploadedFile(
                "source.png",
                base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="),
                content_type="image/png",
            ),
        )
        self.client.force_login(staff)

        prefix = f"product-{product.pk}"
        response = self.client.post(reverse("staff_quick_publish_product", args=[product.pk]), {
            f"{prefix}-name": "Ready footwear", f"{prefix}-category": category.pk,
            f"{prefix}-description": "Ready for customers", f"{prefix}-product_type": "preorder",
            f"{prefix}-rmb_price": "100.00", f"{prefix}-stock_quantity": "0",
            f"{prefix}-existing_image": source_image.pk,
            f"{prefix}-confirm_image_is_customer_safe": "on",
        })

        self.assertRedirects(response, reverse("profile"))
        product.refresh_from_db()
        self.assertEqual(product.status, "active")
        self.assertTrue(product.gallery_images.filter(customer_image__isnull=False, visibility="public").exists())

    def test_staff_can_split_grouped_supplier_photos_into_separate_drafts(self):
        staff = get_user_model().objects.create_user("split-admin", password="pass", is_staff=True)
        category = Category.objects.create(name="Shoes")
        grouped = Product.objects.create(
            name="Grouped shoes", description="Supplier shoes", category=category,
            rmb_price="100", product_type="preorder", status="draft", is_available=False,
        )
        submission = SupplierProductRequest.objects.create(
            submitted_by=staff, converted_product=grouped, supplier_name="Supplier",
            product_name="Grouped shoes", description="Supplier shoes", category=category,
            rmb_price="100", is_reviewed=True, is_approved=True,
        )
        image_ids = []
        for filename in ("w51.png", "s10.png"):
            source = SupplierProductRequestImage.objects.create(
                supplier_request=submission,
                image=SimpleUploadedFile(
                    filename,
                    base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="),
                    content_type="image/png",
                ),
            )
            image_ids.append(source.pk)
        self.client.force_login(staff)
        data = {}
        for image_id, name, price in zip(image_ids, ("W51", "S10"), ("150", "100")):
            data.update({
                f"include_{image_id}": "on", f"name_{image_id}": name,
                f"price_{image_id}": price, f"stock_{image_id}": "30",
                f"sizes_{image_id}": "37, 38", f"colors_{image_id}": "Black, White",
            })

        response = self.client.post(reverse("staff_split_product", args=[grouped.pk]), data)

        self.assertRedirects(response, reverse("profile"))
        grouped.refresh_from_db()
        self.assertEqual(grouped.status, "archived")
        split_products = Product.objects.filter(name__in=["W51", "S10"])
        self.assertEqual(split_products.count(), 2)
        self.assertTrue(all(item.status == "draft" for item in split_products))
        self.assertTrue(all(item.gallery_images.filter(visibility="private", original_image__isnull=False).exists() for item in split_products))

    @patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"})
    @patch("core.views.requests.post")
    def test_staff_can_detect_split_product_details_from_photo(self, post_mock):
        staff = get_user_model().objects.create_user("vision-admin", password="pass", is_staff=True)
        grouped = Product.objects.create(
            name="Grouped", description="Supplier products", rmb_price="100",
            product_type="preorder", status="draft", is_available=False,
        )
        submission = SupplierProductRequest.objects.create(
            converted_product=grouped, supplier_name="Supplier", product_name="Grouped",
            description="Supplier products", rmb_price="100", is_reviewed=True, is_approved=True,
        )
        source = SupplierProductRequestImage.objects.create(
            supplier_request=submission,
            image=SimpleUploadedFile(
                "w51.png",
                base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="),
                content_type="image/png",
            ),
        )
        response_mock = SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"choices": [{"message": {"content": json.dumps({
                "product_name": "Footwear Model W51", "supplier_price_rmb": 150,
                "sizes": "37, 38, 39, 40, 41", "colors": "White, Grey", "confidence": "high",
            })}}]},
        )
        post_mock.return_value = response_mock
        self.client.force_login(staff)

        response = self.client.post(reverse("staff_analyze_split_photo", args=[grouped.pk, source.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["product_name"], "Footwear Model W51")
        self.assertEqual(response.json()["supplier_price_rmb"], "150.00")
        self.assertEqual(response.json()["sizes"], "37, 38, 39, 40, 41")

    def test_staff_can_edit_published_product_from_profile(self):
        staff = get_user_model().objects.create_user("product-admin", password="pass", is_staff=True)
        category = Category.objects.create(name="Fashion")
        product = Product.objects.create(
            name="Old name", description="Old description", category=category,
            rmb_price="35", product_type="local", stock_quantity=5,
            status="active", is_available=True,
        )
        self.client.force_login(staff)
        prefix = f"shop-product-{product.pk}"
        response = self.client.post(reverse("staff_update_shop_product", args=[product.pk]), {
            f"{prefix}-name": "Updated shirt", f"{prefix}-category": category.pk,
            f"{prefix}-description": "Updated description", f"{prefix}-product_type": "local",
            f"{prefix}-rmb_price": "40", f"{prefix}-stock_quantity": "10",
            f"{prefix}-available_quantity": "", f"{prefix}-size_options": "M, L",
            f"{prefix}-color_options": "Black, White", f"{prefix}-status": "active",
            f"{prefix}-is_available": "on", f"{prefix}-is_featured": "on",
        })

        self.assertEqual(response.status_code, 302)
        product.refresh_from_db()
        self.assertEqual(product.name, "Updated shirt")
        self.assertEqual(product.stock_quantity, 10)
        self.assertEqual(product.color_options, "Black, White")

    def test_staff_profile_delete_is_recoverable_soft_delete(self):
        staff = get_user_model().objects.create_user("delete-admin", password="pass", is_staff=True)
        product = Product.objects.create(
            name="Remove me", description="Product", rmb_price="20",
            product_type="preorder", status="active", is_available=True,
        )
        self.client.force_login(staff)

        response = self.client.post(
            reverse("staff_delete_shop_product", args=[product.pk]), {"confirm_delete": "on"}
        )

        self.assertRedirects(response, reverse("profile"))
        product.refresh_from_db()
        self.assertTrue(product.is_deleted)
        self.assertFalse(product.is_available)
        self.assertEqual(product.status, "archived")
