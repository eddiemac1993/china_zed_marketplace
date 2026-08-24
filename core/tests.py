from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from .forms import CustomUserRegistrationForm
from .models import (
    Cart,
    CartItem,
    CustomerProductRequest,
    ExchangeRate,
    Order,
    Product,
)


@override_settings(
    ALLOWED_HOSTS=["testserver"],
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    DEFAULT_FROM_EMAIL="test@chinatozambia.org",
)
class MarketplaceFlowTests(TestCase):
    def setUp(self):
        self.rate = ExchangeRate.objects.create(
            rmb_to_zmw=Decimal("3.20"),
            markup_percentage=Decimal("35.00"),
            deposit_percentage=Decimal("35.00"),
            is_active=True,
        )

    def create_user(self, username="buyer", email="buyer@example.com"):
        return User.objects.create_user(
            username=username,
            email=email,
            password="Str0ngPass!2026",
        )

    def create_preorder_product(self, name="Test Headphones"):
        return Product.objects.create(
            name=name,
            description="Reliable product for marketplace tests.",
            rmb_price=Decimal("100.00"),
            product_type="preorder",
            status="active",
            is_available=True,
            delivery_min_days=14,
            delivery_max_days=30,
        )

    def test_public_pages_load(self):
        for url_name in ["home", "about", "faq", "register", "terms", "privacy", "registration_pending", "assistant"]:
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200)

    def test_homepage_exposes_mobile_app_manifest(self):
        response = self.client.get(reverse("home"))

        self.assertContains(response, 'rel="manifest"')
        self.assertContains(response, "serviceWorker")

    def test_service_worker_is_served_from_site_root(self):
        response = self.client.get(reverse("chinazed_service_worker"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/javascript")
        self.assertEqual(response["Service-Worker-Allowed"], "/")
        self.assertContains(response, "chinazed-app-v2")

    def test_service_worker_does_not_cache_live_endpoints(self):
        response = self.client.get(reverse("chinazed_service_worker"))

        # only /static/ may be served cache-first; chat polling and other live
        # GETs must fall through to the network
        self.assertContains(response, 'startsWith("/static/")')

    @patch.dict("os.environ", {"OPENAI_API_KEY": ""})
    def test_assistant_chat_returns_fallback_reply_without_api_key(self):
        response = self.client.post(
            reverse("assistant_chat"),
            data='{"message":"How does the deposit work?"}',
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("35% deposit", response.json()["reply"])

    def test_product_uses_35_percent_deposit(self):
        product = self.create_preorder_product()

        self.assertEqual(product.selling_price(), Decimal("432.00"))
        self.assertEqual(product.deposit_amount(), Decimal("151.20"))
        self.assertEqual(product.balance_amount(), Decimal("280.80"))

    def test_registration_requires_terms_and_blocks_temporary_email(self):
        missing_terms = CustomUserRegistrationForm(
            data={
                "username": "newbuyer",
                "email": "newbuyer@example.com",
                "password1": "Str0ngPass!2026",
                "password2": "Str0ngPass!2026",
            }
        )
        self.assertFalse(missing_terms.is_valid())
        self.assertIn("accept_terms", missing_terms.errors)

        temporary_email = CustomUserRegistrationForm(
            data={
                "username": "tempbuyer",
                "email": "tempbuyer@mailinator.com",
                "password1": "Str0ngPass!2026",
                "password2": "Str0ngPass!2026",
                "accept_terms": "on",
            }
        )
        self.assertFalse(temporary_email.is_valid())
        self.assertIn("Please use a permanent email address.", temporary_email.errors["email"])

    def test_registration_creates_inactive_user_and_sends_activation_email(self):
        response = self.client.post(
            reverse("register"),
            {
                "email": "verifyme@example.com",
                "password1": "Str0ngPass!2026",
                "password2": "Str0ngPass!2026",
                "accept_terms": "on",
            },
        )

        self.assertRedirects(response, reverse("registration_pending"))
        user = User.objects.get(email="verifyme@example.com")
        self.assertTrue(user.username.startswith("verifyme-"))
        self.assertFalse(user.is_active)
        self.assertEqual(user.email, "verifyme@example.com")
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Activate your ChinaZed account", mail.outbox[0].subject)

        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        activation_response = self.client.get(
            reverse("activate_account", kwargs={"uidb64": uid, "token": token})
        )

        self.assertRedirects(activation_response, reverse("login"))
        user.refresh_from_db()
        self.assertTrue(user.is_active)

    def test_users_can_log_in_with_email_or_legacy_username(self):
        user = User.objects.create_user(
            username="legacybuyer",
            email="legacy@example.com",
            password="Str0ngPass!2026",
        )

        self.assertTrue(self.client.login(username=user.email, password="Str0ngPass!2026"))
        self.client.logout()
        self.assertTrue(self.client.login(username=user.username, password="Str0ngPass!2026"))

    def test_request_product_requires_login_and_saves_customer_request(self):
        response = self.client.get(reverse("request_product"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response["Location"])

        user = self.create_user()
        self.client.force_login(user)

        response = self.client.post(
            reverse("request_product"),
            {
                "product_name": "Running shoes",
                "product_link": "https://www.alibaba.com/product-detail/example",
                "source_platform": "alibaba",
                "notes": "Size 42, black.",
            },
        )

        self.assertRedirects(response, reverse("profile"))
        product_request = CustomerProductRequest.objects.get(user=user)
        self.assertEqual(product_request.product_name, "Running shoes")
        self.assertEqual(product_request.status, "new")

    def test_quoted_product_request_calculates_deposit_and_shows_on_profile(self):
        user = self.create_user()
        product_request = CustomerProductRequest.objects.create(
            user=user,
            product_name="Smart watch",
            product_link="https://www.temu.com/example",
            source_platform="temu",
            status="quoted",
            quoted_price=Decimal("1000.00"),
            customer_message="Quote includes estimated shipping to Zambia.",
        )

        product_request.refresh_from_db()
        self.assertEqual(product_request.quoted_deposit, Decimal("350.00"))
        self.assertIsNotNone(product_request.quoted_at)

        self.client.force_login(user)
        response = self.client.get(reverse("profile"))

        self.assertContains(response, "Smart watch")
        self.assertContains(response, "K1,000")
        self.assertContains(response, "K350")

    def test_cart_checkout_creates_order_with_35_percent_deposit(self):
        user = self.create_user()
        product = self.create_preorder_product()
        cart = Cart.objects.create(user=user)
        CartItem.objects.create(cart=cart, product=product, quantity=2)

        self.client.force_login(user)
        response = self.client.post(
            reverse("checkout_cart"),
            {
                "customer_phone": "0970000000",
                "customer_note": "Please confirm before buying.",
            },
        )

        self.assertRedirects(response, reverse("order_detail", kwargs={"order_id": Order.objects.get(user=user).id}))

        order = Order.objects.get(user=user)
        self.assertEqual(order.total_price, Decimal("864.00"))
        self.assertEqual(order.deposit_percentage_used, Decimal("35.00"))
        self.assertEqual(order.deposit_amount, Decimal("302.40"))
        self.assertEqual(order.balance_amount, Decimal("561.60"))
        self.assertEqual(order.items.count(), 1)
        self.assertFalse(cart.items.exists())

        profile_response = self.client.get(reverse("profile"))
        self.assertContains(profile_response, "item-thumb")
        self.assertContains(profile_response, product.name)

    def test_product_display_image_url_prefers_external_image_when_no_upload(self):
        product = self.create_preorder_product(name="External image item")
        product.external_image_url = "https://example.com/product.png"
        product.external_gallery_urls = "https://example.com/product-blue.png\nhttps://example.com/product-red.png"
        product.available_quantity = 25
        product.size_options = "S, M, L"
        product.color_options = "Black, Blue"
        product.save(update_fields=[
            "external_image_url",
            "external_gallery_urls",
            "available_quantity",
            "size_options",
            "color_options",
        ])

        self.assertEqual(product.display_image_url(), "https://example.com/product.png")
        self.assertEqual(
            product.display_gallery_urls(),
            [
                "https://example.com/product.png",
                "https://example.com/product-blue.png",
                "https://example.com/product-red.png",
            ],
        )
        self.assertEqual(product.size_option_list(), ["S", "M", "L"])
        self.assertEqual(product.color_option_list(), ["Black", "Blue"])
        self.assertEqual(product.availability_label(), "Supplier availability: 25")

        response = self.client.get(reverse("home"))
        self.assertContains(response, "https://example.com/product.png")

        detail_response = self.client.get(reverse("product_detail", kwargs={"slug": product.slug}))
        self.assertContains(detail_response, "https://example.com/product-blue.png")
        self.assertContains(detail_response, "Tap to zoom")
        self.assertContains(detail_response, "Supplier availability: 25")
        self.assertContains(detail_response, "Black")
        self.assertContains(detail_response, "S")

