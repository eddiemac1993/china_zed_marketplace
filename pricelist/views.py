from django.shortcuts import render, get_object_or_404
from .models import PriceList


def price_list_view(request, pk):
    price_list = get_object_or_404(PriceList, pk=pk)
    items = price_list.items.all()

    context = {
        "price_list": price_list,
        "items": items,
        "total": price_list.total_amount(),
    }

    return render(request, "pricelist/price_list.html", context)


from django.db.models import Sum

def price_list_index(request):

    price_lists = PriceList.objects.all().order_by("-date")

    grand_total = sum(
        pl.total_amount()
        for pl in price_lists
    )

    context = {
        "price_lists": price_lists,
        "grand_total": grand_total,
    }

    return render(
        request,
        "pricelist/index.html",
        context
    )