from datetime import timedelta
from decimal import Decimal

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class SupplierProductBackfillMigrationTests(TransactionTestCase):
    migrate_from = [("core", "0040_seed_footwear_category")]
    migrate_to = [("core", "0041_supplierproductrequest_converted_product")]

    def test_one_draft_is_not_linked_to_multiple_legacy_submissions(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        Product = old_apps.get_model("core", "Product")
        Submission = old_apps.get_model("core", "SupplierProductRequest")

        draft = Product.objects.create(
            name="New product",
            description="Draft",
            rmb_price=Decimal("100.00"),
            status="draft",
            is_available=False,
        )
        first = Submission.objects.create(
            supplier_name="Admin",
            product_name="New product",
            description="First",
            rmb_price=Decimal("100.00"),
            is_reviewed=True,
            is_approved=True,
        )
        second = Submission.objects.create(
            supplier_name="Admin",
            product_name="New product",
            description="Second",
            rmb_price=Decimal("100.00"),
            is_reviewed=True,
            is_approved=True,
        )
        matching_time = timezone.now()
        Product.objects.filter(pk=draft.pk).update(created_at=matching_time)
        Submission.objects.filter(pk__in=[first.pk, second.pk]).update(
            created_at=matching_time - timedelta(minutes=1)
        )

        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_to)
        new_apps = executor.loader.project_state(self.migrate_to).apps
        migrated = new_apps.get_model("core", "SupplierProductRequest").objects.filter(
            converted_product__isnull=False
        )
        self.assertEqual(migrated.count(), 1)

    def tearDown(self):
        MigrationExecutor(connection).migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())
        super().tearDown()
