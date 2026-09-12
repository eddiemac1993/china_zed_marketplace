from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase
from core.models import ExchangeRate, Product, ProductVariant


class OrderDiscountTests(TestCase):
    def test_default_and_fallback_apply_at_ten_units(self):
        self.assertEqual(ExchangeRate().wholesale_discount_percentage, Decimal("23.00"))
        product = Product()
        variant = ProductVariant(product=product, selling_price_override=Decimal("122.40"))
        with patch.object(Product, "active_exchange_rate", return_value=None), patch.object(Product, "selling_price", return_value=Decimal("122.40")):
            for item in (product, variant):
                self.assertEqual(item.unit_price_for_quantity(9), Decimal("122.40"))
                self.assertEqual(item.unit_price_for_quantity(10), Decimal("94.25"))

    def test_migration_updates_active_settings_and_prices(self):
        from importlib import import_module
        from django.apps import apps
        from django.db import connection
        from types import SimpleNamespace
        active = ExchangeRate.objects.create(rmb_to_zmw=Decimal("3.20"), wholesale_discount_percentage=10)
        inactive = ExchangeRate.objects.create(rmb_to_zmw=Decimal("3.20"), is_active=False, wholesale_discount_percentage=10)
        import_module("core.migrations.0056_order_price_discount_23").set_active_discount(apps, SimpleNamespace(connection=connection))
        active.refresh_from_db()
        inactive.refresh_from_db()
        self.assertEqual(active.wholesale_discount_percentage, Decimal("23.00"))
        self.assertEqual(inactive.wholesale_discount_percentage, Decimal("10.00"))
        with patch.object(Product, "selling_price", return_value=Decimal("122.40")):
            self.assertEqual(Product().unit_price_for_quantity(10), Decimal("94.25"))
