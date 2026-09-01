import base64
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from django.contrib.auth.models import User

from core.models import Advertisement, Category, MarketplaceEvent, Order, Product, WishlistItem


@override_settings(ALLOWED_HOSTS=["testserver"], SECURE_SSL_REDIRECT=False)
class AdvertisementSubmissionTests(TestCase):
    def setUp(self):
        Product.objects.create(
            name="Grid product",
            description="A product used to verify sponsored grid cards.",
            rmb_price="100.00",
            product_type="preorder",
            status="active",
            is_available=True,
        )

    def test_any_visitor_can_open_advertising_form(self):
        response = self.client.get(reverse("advertise"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Upload my ad")
        self.assertNotContains(response, "Advertiser name")

    def test_public_submission_goes_live_and_appears_as_product_sized_card(self):
        image = SimpleUploadedFile("advert.png", base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        ), content_type="image/png")
        response = self.client.post(reverse("advertise"), {"image": image})

        advertisement = Advertisement.objects.get()
        self.assertRedirects(response, reverse("advertise_success", kwargs={"ad_id": advertisement.pk}))
        self.assertTrue(advertisement.is_active)
        self.assertIsNotNone(advertisement.display_from)

        success = self.client.get(response["Location"])
        self.assertContains(success, "Your advert is live!")
        self.assertContains(success, advertisement.image.url)

        home = self.client.get(reverse("home"))
        self.assertContains(home, advertisement.image.url)
        self.assertContains(home, "Sponsored")

    def test_future_and_inactive_ads_do_not_appear(self):
        Advertisement.objects.create(
            advertiser_name="Hidden advertiser",
            headline="This should stay hidden",
            cta_url="https://example.com",
            is_active=False,
        )

        home = self.client.get(reverse("home"))
        self.assertNotContains(home, "This should stay hidden")

    def test_homepage_shows_zambian_shopping_shortcuts_and_real_trust_copy(self):
        home = self.client.get(reverse("home"))

        self.assertContains(home, "Pay with Mobile Money")
        self.assertContains(home, "MTN MoMo")
        self.assertContains(home, "TRENDING IN ZAMBIA")
        self.assertContains(home, "Ask on WhatsApp")
        self.assertNotContains(home, "1,247")
        self.assertNotContains(home, "people browsing now")

    def test_search_product_view_and_whatsapp_click_are_recorded(self):
        product = Product.objects.get(name="Grid product")

        self.client.get(reverse("home"), {"q": "Grid"})
        self.client.get(reverse("home"), {"q": "Not sold here"})
        self.client.get(reverse("product_detail", kwargs={"slug": product.slug}))
        whatsapp = self.client.get(reverse("product_whatsapp", kwargs={"slug": product.slug}))

        self.assertEqual(whatsapp.status_code, 302)
        self.assertTrue(whatsapp["Location"].startswith("https://wa.me/"))
        self.assertTrue(MarketplaceEvent.objects.filter(event_type="search", search_query="Grid").exists())
        self.assertTrue(MarketplaceEvent.objects.filter(event_type="zero_search", search_query="Not sold here").exists())
        self.assertTrue(MarketplaceEvent.objects.filter(event_type="product_view", product=product).exists())
        self.assertTrue(MarketplaceEvent.objects.filter(event_type="whatsapp_click", product=product).exists())
        product.refresh_from_db()
        self.assertEqual(product.views_count, 1)

    def test_successful_order_is_recorded_only_once(self):
        user = User.objects.create_user(username="analytics-buyer", password="test-pass")
        order = Order.objects.create(user=user, total_price="550.00")

        order.status = "successful"
        order.save()
        order.save()

        events = MarketplaceEvent.objects.filter(event_type="completed_order", order=order)
        self.assertEqual(events.count(), 1)
        self.assertEqual(events.get().value, Decimal("550.00"))

    def test_add_to_cart_conversion_is_recorded(self):
        user = User.objects.create_user(username="cart-analytics", password="test-pass")
        category = Category.objects.create(name="Analytics products")
        product = Product.objects.get(name="Grid product")
        product.category = category
        product.external_image_url = "https://example.com/product.jpg"
        product.save()
        self.client.force_login(user)

        response = self.client.post(reverse("add_to_cart", kwargs={"slug": product.slug}), {"quantity": 2})

        self.assertRedirects(response, reverse("cart"))
        event = MarketplaceEvent.objects.get(event_type="add_to_cart", product=product)
        self.assertEqual(event.quantity, 2)
        self.assertEqual(event.user, user)

    def test_user_can_save_and_remove_a_product(self):
        user = User.objects.create_user(username="wishlist-buyer", password="test-pass")
        product = Product.objects.get(name="Grid product")
        self.client.force_login(user)

        save = self.client.post(reverse("toggle_wishlist", kwargs={"slug": product.slug}))
        self.assertRedirects(save, reverse("wishlist"))
        self.assertTrue(WishlistItem.objects.filter(user=user, product=product).exists())
        saved_page = self.client.get(reverse("wishlist"))
        self.assertContains(saved_page, product.name)

        self.client.post(reverse("toggle_wishlist", kwargs={"slug": product.slug}))
        self.assertFalse(WishlistItem.objects.filter(user=user, product=product).exists())
