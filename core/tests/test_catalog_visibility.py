from unittest.mock import patch
from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from core.models import Category, Product


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=["testserver"])
class CatalogVisibilityTests(TestCase):
    def test_turning_on_activates_ready_stocked_product(self):
        staff = User.objects.create_user("publish-staff", is_staff=True)
        self.client.force_login(staff)
        Product.objects.filter(pk=self.live.pk).update(status="out_of_stock", is_available=False, show_on_homepage=False)
        response = self.client.post(reverse("staff_product_homepage", args=[self.live.pk]),
                                    {"visible": "1"}, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 200)
        self.live.refresh_from_db()
        self.assertEqual(self.live.status, "active")
        self.assertTrue(self.live.is_available)
        self.assertIn(self.live, self.client.get(reverse("home")).context["products"])

    def test_turning_on_rejects_zero_stock(self):
        staff = User.objects.create_user("empty-stock-staff", is_staff=True)
        self.client.force_login(staff)
        Product.objects.filter(pk=self.live.pk).update(stock_quantity=0, show_on_homepage=False)
        response = self.client.post(reverse("staff_product_homepage", args=[self.live.pk]),
                                    {"visible": "1"}, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 400)
        self.live.refresh_from_db()
        self.assertFalse(self.live.show_on_homepage)

    def test_migration_repairs_only_stocked_enabled_products(self):
        from importlib import import_module
        from django.apps import apps
        from django.db import connection
        from types import SimpleNamespace
        Product.objects.filter(pk__in=[self.live.pk, self.hidden[0].pk]).update(status="out_of_stock")
        migration = import_module("core.migrations.0055_restore_stocked_homepage_products")
        migration.restore_stocked_products(apps, SimpleNamespace(connection=connection))
        self.live.refresh_from_db()
        self.hidden[0].refresh_from_db()
        self.assertEqual(self.live.status, "active")
        self.assertEqual(self.hidden[0].status, "out_of_stock")

    def setUp(self):
        self.category = Category.objects.create(name="Catalog tests")
        self.live = self.product("visible", stock_quantity=3)
        self.hidden = [
            self.product("switched-off", stock_quantity=3, show_on_homepage=False),
            self.product("unavailable", stock_quantity=3, is_available=False),
            self.product("draft", stock_quantity=3, status="draft"),
            self.product("deleted", stock_quantity=3, is_deleted=True),
            self.product("sold-out", stock_quantity=0),
            self.product("supplier-empty", product_type="preorder", available_quantity=0),
        ]
        self.preorder = self.product("preorder", product_type="preorder", stock_quantity=0, available_quantity=None)
        # Imports/bulk inventory updates may leave zero-stock rows active.
        Product.objects.filter(pk=self.hidden[4].pk).update(status="active")

    def product(self, name, **kwargs):
        data = dict(name="Visibility " + name, description="Product", category=self.category,
                    product_type="local", rmb_price=20, is_featured=True, status="active",
                    is_available=True, show_on_homepage=True, external_image_url="https://example.com/image.png")
        data.update(kwargs)
        return Product.objects.create(**data)

    def test_every_homepage_section_excludes_hidden_and_empty_products(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        forbidden = {p.pk for p in self.hidden}
        for section in ["products", "featured_products", "local_products", "preorder_products", "trending_products", "budget_products"]:
            self.assertFalse(forbidden.intersection(p.pk for p in response.context[section]), section)
        self.assertIn(self.live, response.context["products"])
        self.assertIn(self.preorder, response.context["products"])
        self.assertIn("no-store", response["Cache-Control"])

    def test_suggestions_recommendations_and_history_use_same_rule(self):
        for route, query in [("search_suggestions", {"q": "Visibility"}),
                             ("home_recommendations", {"categories": str(self.category.pk)})]:
            response = self.client.get(reverse(route), query)
            for product in self.hidden:
                self.assertNotContains(response, product.name)
            self.assertContains(response, self.live.name)
            self.assertIn("no-store", response["Cache-Control"])
        with patch("core.views.has_optional_consent", return_value=True):
            response = self.client.get(reverse("visible_history_products"),
                {"slugs": ",".join(p.slug for p in [self.live, self.preorder] + self.hidden)})
        self.assertSetEqual(set(response.json()["slugs"]), {self.live.slug, self.preorder.slug})

    def test_switch_off_and_stock_change_apply_on_next_home_request(self):
        staff = User.objects.create_user("catalog-staff", is_staff=True)
        self.client.force_login(staff)
        response = self.client.post(reverse("staff_product_homepage", args=[self.live.pk]),
                                    {"visible": "0"}, HTTP_ACCEPT="application/json")
        self.assertEqual(response.json(), {"visible": False})
        self.assertNotIn(self.live, self.client.get(reverse("home")).context["products"])
        self.live.refresh_from_db()
        self.live.show_on_homepage = True
        self.live.stock_quantity = 0
        self.live.save()
        self.assertNotIn(self.live, self.client.get(reverse("home")).context["products"])
        self.live.stock_quantity = 2
        self.live.status = "active"
        self.live.save()
        self.assertIn(self.live, self.client.get(reverse("home")).context["products"])

    def test_profile_editor_accepts_zero_and_blank_stock_and_persists_it(self):
        staff = User.objects.create_user("stock-editor", is_staff=True)
        self.client.force_login(staff)
        for stock in ("0", ""):
            self.live.stock_quantity = 3
            self.live.save()
            fields = {"name": self.live.name, "category": self.category.pk, "description": "Product",
                      "product_type": "local", "rmb_price": "20", "stock_quantity": stock,
                      "status": "active", "is_available": "on", "is_featured": "on"}
            response = self.client.post(reverse("staff_update_shop_product", args=[self.live.pk]),
                {f"shop-product-{self.live.pk}-{key}": value for key, value in fields.items()})
            self.assertEqual(response.status_code, 302)
            self.live.refresh_from_db()
            self.assertEqual(self.live.stock_quantity, 0)
            self.assertNotIn(self.live, self.client.get(reverse("home")).context["products"])
