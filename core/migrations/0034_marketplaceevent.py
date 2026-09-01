from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0033_exchangerate_biker_fee_share_percentage_biker_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="MarketplaceEvent",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("event_type", models.CharField(choices=[("search", "Search"), ("zero_search", "Search with no results"), ("product_view", "Product view"), ("whatsapp_click", "WhatsApp click"), ("add_to_cart", "Add to cart"), ("completed_order", "Completed order")], db_index=True, max_length=30)),
                ("session_key", models.CharField(blank=True, db_index=True, max_length=40)),
                ("search_query", models.CharField(blank=True, db_index=True, max_length=200)),
                ("result_count", models.PositiveIntegerField(blank=True, null=True)),
                ("quantity", models.PositiveIntegerField(blank=True, null=True)),
                ("value", models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True)),
                ("path", models.CharField(blank=True, max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("order", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="marketplace_events", to="core.order")),
                ("product", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="marketplace_events", to="core.product")),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="marketplace_events", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.AddConstraint(
            model_name="marketplaceevent",
            constraint=models.UniqueConstraint(fields=("event_type", "order"), name="unique_completed_order_event"),
        ),
    ]
