from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.management import call_command
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


class FakeResponse:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


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
        response = self.client.get(reverse("service_worker"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/javascript")
        self.assertEqual(response["Service-Worker-Allowed"], "/")
        self.assertContains(response, "chinazed-app-v1")

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
                "username": "verifyme",
                "email": "verifyme@example.com",
                "password1": "Str0ngPass!2026",
                "password2": "Str0ngPass!2026",
                "accept_terms": "on",
            },
        )

        self.assertRedirects(response, reverse("registration_pending"))
        user = User.objects.get(username="verifyme")
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

    @patch("core.management.commands.import_aliexpress_products.requests.get")
    def test_import_aliexpress_product_creates_preorder_product(self, mock_get):
        html = """
        <html>
            <head>
                <script type="application/ld+json">
                {
                    "@type": "Product",
                    "name": "Portable Mini Projector",
                    "description": "Compact projector for home entertainment.",
                    "image": "https://example.com/projector.jpg",
                    "offers": {
                        "price": "25.50",
                        "priceCurrency": "USD"
                    }
                }
                </script>
            </head>
        </html>
        """
        mock_get.return_value = FakeResponse(html)
        out = StringIO()

        call_command(
            "import_aliexpress_products",
            "https://www.aliexpress.com/item/100500-example.html",
            "--category",
            "Electronics",
            "--status",
            "active",
            "--usd-to-rmb",
            "7.20",
            stdout=out,
        )

        product = Product.objects.get(source_platform="aliexpress")
        self.assertEqual(product.name, "Portable Mini Projector")
        self.assertEqual(product.rmb_price, Decimal("183.60"))
        self.assertEqual(product.product_type, "preorder")
        self.assertEqual(product.status, "active")
        self.assertEqual(product.category.name, "Electronics")
