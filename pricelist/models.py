from django.db import models
from django.utils import timezone


class PriceList(models.Model):
    title = models.CharField(max_length=200)
    client_name = models.CharField(max_length=200, blank=True, null=True)
    reference_no = models.CharField(max_length=100, blank=True, null=True)
    date = models.DateField(default=timezone.now)

    def __str__(self):
        return self.title

    def total_amount(self):
        return sum(item.total_price() for item in self.items.all())


class PriceListItem(models.Model):
    price_list = models.ForeignKey(
        PriceList,
        on_delete=models.CASCADE,
        related_name="items"
    )
    item_name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    where_to_buy = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return self.item_name

    def total_price(self):
        return self.quantity * self.unit_price