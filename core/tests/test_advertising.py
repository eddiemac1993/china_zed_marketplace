from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import Advertisement, Product


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
        self.assertContains(response, "Post my ad")

    def test_public_submission_goes_live_and_appears_as_product_sized_card(self):
        response = self.client.post(reverse("advertise"), {
            "advertiser_name": "Zed Services",
            "headline": "Fast delivery across Lusaka",
            "subtext": "Same-day deliveries available.",
            "cta_text": "Book now",
            "cta_url": "https://example.com/book",
        })

        self.assertRedirects(response, reverse("home"))
        advertisement = Advertisement.objects.get()
        self.assertTrue(advertisement.is_active)
        self.assertIsNotNone(advertisement.display_from)

        home = self.client.get(reverse("home"))
        self.assertContains(home, "Fast delivery across Lusaka")
        self.assertContains(home, "Sponsored")
        self.assertContains(home, 'rel="noopener sponsored"')

    def test_future_and_inactive_ads_do_not_appear(self):
        Advertisement.objects.create(
            advertiser_name="Hidden advertiser",
            headline="This should stay hidden",
            cta_url="https://example.com",
            is_active=False,
        )

        home = self.client.get(reverse("home"))
        self.assertNotContains(home, "This should stay hidden")
