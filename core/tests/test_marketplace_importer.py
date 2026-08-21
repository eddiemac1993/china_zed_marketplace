from pathlib import Path
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from core.marketplace_importer import (
    ImportFailure,
    detect_platform,
    parse_marketplace_html,
    safe_get,
)


FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name):
    return (FIXTURES / name).read_text(encoding="utf-8")


class MarketplaceParserTests(SimpleTestCase):
    def test_complete_import_and_variant_price_range(self):
        result = parse_marketplace_html(
            "aliexpress",
            "https://www.aliexpress.com/item/1005001234567890.html",
            fixture("complete.html"),
        )
        self.assertEqual(result.product_id, "1005001234567890")
        self.assertEqual(result.title, "Women Denim Jacket")
        self.assertEqual(result.price_min, "12.50")
        self.assertEqual(result.price_max, "18.75")
        self.assertEqual(result.currency, "USD")
        self.assertEqual(result.colors, ["Blue", "Black"])
        self.assertEqual(result.sizes, ["S", "M"])
        self.assertEqual(len(result.image_urls), 2)
        result.local_image_paths = ["supplier_imports/1/cover.jpg"]
        self.assertTrue(result.complete)

    def test_partial_import_does_not_claim_success(self):
        result = parse_marketplace_html(
            "aliexpress",
            "https://www.aliexpress.com/item/1005009999999999.html",
            fixture("partial.html"),
        )
        payload = result.as_dict()
        self.assertEqual(payload["status"], "partial")
        self.assertIn("Basic information imported", payload["status_message"])
        self.assertIn("Price unavailable", " ".join(payload["warnings"]))

    def test_missing_images_is_reported(self):
        result = parse_marketplace_html(
            "aliexpress",
            "https://www.aliexpress.com/item/1005008888888888.html",
            fixture("missing_images.html"),
        )
        self.assertEqual(result.image_urls, [])
        self.assertIn("Images unavailable", " ".join(result.warnings))
        self.assertFalse(result.complete)

    def test_removed_product_fixture(self):
        with self.assertRaises(ImportFailure) as error:
            parse_marketplace_html(
                "aliexpress",
                "https://www.aliexpress.com/item/1005007777777777.html",
                fixture("removed.html"),
            )
        self.assertEqual(error.exception.code, "product_removed")

    def test_share_and_mobile_hosts_are_supported(self):
        self.assertEqual(detect_platform("https://a.aliexpress.com/_mExample"), "aliexpress")
        self.assertEqual(detect_platform("https://m.aliexpress.com/item/1005001234567890.html"), "aliexpress")
        self.assertEqual(detect_platform("https://e.tb.cn/h.example"), "taobao")

    def test_blocked_url_is_rejected(self):
        with self.assertRaises(ImportFailure) as error:
            detect_platform("http://127.0.0.1/admin")
        self.assertEqual(error.exception.code, "unsupported_link")


class RedirectSafetyTests(SimpleTestCase):
    @patch("core.marketplace_importer.socket.getaddrinfo")
    def test_redirect_to_private_address_is_blocked(self, getaddrinfo):
        getaddrinfo.side_effect = lambda host, *args, **kwargs: [
            (2, 1, 6, "", ("127.0.0.1" if host == "127.0.0.1" else "93.184.216.34", 443))
        ]
        response = Mock()
        response.status_code = 302
        response.headers = {"Location": "http://127.0.0.1/private"}
        response.close = Mock()
        session = Mock()
        session.get.return_value = response
        with self.assertRaises(ImportFailure) as error:
            safe_get(
                "https://www.aliexpress.com/item/1005001234567890.html",
                {"www.aliexpress.com"},
                session=session,
            )
        self.assertIn(error.exception.code, {"blocked_redirect", "blocked_address"})

    @patch("core.marketplace_importer.socket.getaddrinfo")
    def test_redirect_to_unapproved_public_host_is_blocked(self, getaddrinfo):
        getaddrinfo.return_value = [(2, 1, 6, "", ("93.184.216.34", 443))]
        response = Mock()
        response.status_code = 302
        response.headers = {"Location": "https://example.com/product"}
        response.close = Mock()
        session = Mock()
        session.get.return_value = response
        with self.assertRaises(ImportFailure) as error:
            safe_get(
                "https://www.aliexpress.com/item/1005001234567890.html",
                {"www.aliexpress.com"},
                session=session,
            )
        self.assertEqual(error.exception.code, "blocked_redirect")

