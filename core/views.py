from datetime import date, timedelta
from django.urls import reverse
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import get_template

from xhtml2pdf import pisa
from urllib.parse import quote
from .forms import OrderForm
from .models import Product, Order, Category, SupplierProductRequestImage

from .forms import OrderForm, SupplierProductRequestForm

def home(request):
    query = request.GET.get("q", "")
    category_id = request.GET.get("category", "")

    products = Product.objects.filter(is_available=True).order_by("-created_at")
    categories = Category.objects.all().order_by("name")
    featured_products = Product.objects.filter(is_available=True, is_featured=True).order_by("-created_at")[:8]

    if query:
        products = products.filter(name__icontains=query)

    if category_id:
        products = products.filter(category_id=category_id)

    return render(request, "core/home.html", {
        "products": products,
        "categories": categories,
        "query": query,
        "category_id": category_id,
        "featured_products": featured_products,
    })


def product_detail(request, product_id):
    product = get_object_or_404(Product, id=product_id, is_available=True)

    return render(request, "core/product_detail.html", {
        "product": product,
    })


def register_view(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)

        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, "Account created successfully.")
            return redirect("home")
    else:
        form = UserCreationForm()

    return render(request, "core/register.html", {
        "form": form,
    })


def logout_view(request):
    logout(request)
    return redirect("home")


@login_required
def profile_view(request):
    orders = Order.objects.filter(user=request.user).order_by("-order_date")

    successful_orders = orders.filter(status="successful")
    cancelled_orders = orders.filter(status="cancelled")

    delayed_orders_count = 0
    active_orders_count = 0

    for order in orders:
        if order.is_delayed():
            delayed_orders_count += 1
        elif order.status not in ["successful", "cancelled"]:
            active_orders_count += 1

    return render(request, "core/profile.html", {
        "orders": orders,
        "successful_orders": successful_orders,
        "cancelled_orders": cancelled_orders,
        "delayed_orders_count": delayed_orders_count,
        "active_orders_count": active_orders_count,
    })


@login_required
def place_order_view(request, product_id):
    product = get_object_or_404(Product, id=product_id, is_available=True)

    if request.method == "POST":
        form = OrderForm(request.POST)

        if form.is_valid():
            arrival_start = date.today() + timedelta(days=14)
            arrival_end = date.today() + timedelta(days=30)

            order = Order.objects.create(
                user=request.user,
                product=product,
                total_price=product.selling_price(),
                deposit_amount=product.deposit_amount(),
                balance_amount=product.balance_amount(),
                estimated_arrival_start=arrival_start,
                estimated_arrival_end=arrival_end,
                customer_phone=form.cleaned_data["customer_phone"],
                customer_note=form.cleaned_data["customer_note"],
            )

            order_link = request.build_absolute_uri(
                reverse("order_detail", kwargs={"order_id": order.id})
            )

            whatsapp_message = f"""
Hello, I have placed an order on China Zed Marketplace.

Order ID: #{order.id}
Customer: {request.user.username}
Product: {product.name}
Total Price: K{order.total_price}
Deposit Required: K{order.deposit_amount}
Balance on Arrival: K{order.balance_amount}
Phone: {order.customer_phone}
Expected Arrival: {order.estimated_arrival_start} to {order.estimated_arrival_end}

Please confirm availability and deposit instructions.

Track here:
{order_link}
"""

            whatsapp_url = f"https://wa.me/260772447190?text={quote(whatsapp_message)}"

            return redirect(whatsapp_url)

    else:
        form = OrderForm()

    return render(request, "core/place_order.html", {
        "form": form,
        "product": product,
    })

@login_required
def order_detail_view(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)

    return render(request, "core/order_detail.html", {
        "order": order
    })


@login_required
def receipt_view(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)

    allowed_statuses = ["arrived", "ready", "successful"]

    if order.status not in allowed_statuses:
        messages.error(request, "Receipt is only available once goods have arrived.")
        return redirect("profile")

    if not order.receipt_number:
        order.receipt_number = f"CZM-{order.id:05d}"
        order.save()

    return render(request, "core/receipt.html", {
        "order": order,
    })


@login_required
def receipt_pdf_view(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)

    allowed_statuses = ["arrived", "ready", "successful"]

    if order.status not in allowed_statuses:
        messages.error(request, "Receipt is only available once goods have arrived.")
        return redirect("profile")

    if not order.receipt_number:
        order.receipt_number = f"CZM-{order.id:05d}"
        order.save()

    template = get_template("core/receipt_pdf.html")
    html = template.render({
        "order": order,
    })

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="receipt-{order.receipt_number}.pdf"'

    pisa_status = pisa.CreatePDF(html, dest=response)

    if pisa_status.err:
        return HttpResponse("PDF generation failed", status=500)

    return response


def order_policy(request):
    return render(request, "core/order_policy.html")

def supplier_submit_product(request):
    if request.method == "POST":
        form = SupplierProductRequestForm(request.POST, request.FILES)

        if form.is_valid():
            supplier_request = form.save()

            images = request.FILES.getlist("images")

            for img in images:
                SupplierProductRequestImage.objects.create(
                    supplier_request=supplier_request,
                    image=img
                )

            messages.success(request, "Product submitted successfully.")
            return redirect("supplier_submit_product")
        else:
            print(form.errors)
            messages.error(request, form.errors)
    else:
        form = SupplierProductRequestForm()

    return render(request, "core/supplier_submit_product.html", {
        "form": form,
    })