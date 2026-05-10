from urllib.parse import quote

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import get_template
from django.urls import reverse

from xhtml2pdf import pisa

from .forms import OrderForm, SupplierProductRequestForm
from .models import (
    Product,
    Order,
    OrderItem,
    Cart,
    CartItem,
    Category,
    SupplierProductRequestImage,
)


WHATSAPP_NUMBER = "260969274458"


def get_user_cart(user):
    cart, created = Cart.objects.get_or_create(user=user)
    return cart


def home(request):
    query = request.GET.get("q", "").strip()
    category_id = request.GET.get("category", "").strip()
    product_type = request.GET.get("type", "").strip()

    products = Product.objects.filter(is_available=True).order_by("-created_at")
    categories = Category.objects.all().order_by("name")

    featured_products = Product.objects.filter(
        is_available=True,
        is_featured=True
    ).order_by("-created_at")[:8]

    local_products = Product.objects.filter(
        is_available=True,
        product_type="local",
        stock_quantity__gt=0
    ).order_by("-created_at")[:10]

    preorder_products = Product.objects.filter(
        is_available=True,
        product_type="preorder"
    ).order_by("-created_at")[:10]

    if query:
        products = products.filter(name__icontains=query)

    if category_id:
        products = products.filter(category_id=category_id)

    if product_type in ["local", "preorder"]:
        products = products.filter(product_type=product_type)

    cart_count = 0
    if request.user.is_authenticated:
        cart_count = get_user_cart(request.user).total_items()

    return render(request, "core/home.html", {
        "products": products,
        "categories": categories,
        "query": query,
        "category_id": category_id,
        "product_type": product_type,
        "featured_products": featured_products,
        "local_products": local_products,
        "preorder_products": preorder_products,
        "cart_count": cart_count,
    })


def product_detail(request, slug):
    product = get_object_or_404(
        Product,
        slug=slug,
        is_available=True
    )

    cart_count = 0
    if request.user.is_authenticated:
        cart_count = get_user_cart(request.user).total_items()

    return render(request, "core/product_detail.html", {
        "product": product,
        "cart_count": cart_count,
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

    cart_count = get_user_cart(request.user).total_items()

    return render(request, "core/profile.html", {
        "orders": orders,
        "successful_orders": successful_orders,
        "cancelled_orders": cancelled_orders,
        "delayed_orders_count": delayed_orders_count,
        "active_orders_count": active_orders_count,
        "cart_count": cart_count,
    })


@login_required
def add_to_cart_view(request, slug):
    product = get_object_or_404(
        Product,
        slug=slug,
        is_available=True
    )

    quantity = 1

    if request.method == "POST":
        try:
            quantity = int(request.POST.get("quantity", 1))
        except ValueError:
            quantity = 1

    if quantity < 1:
        quantity = 1

    if product.product_type == "local" and product.stock_quantity <= 0:
        messages.error(request, "This product is currently out of stock.")
        return redirect("product_detail", slug=product.slug)

    cart = get_user_cart(request.user)

    cart_item, created = CartItem.objects.get_or_create(
        cart=cart,
        product=product,
        defaults={"quantity": quantity}
    )

    if not created:
        new_quantity = cart_item.quantity + quantity

        if product.product_type == "local" and new_quantity > product.stock_quantity:
            messages.error(
                request,
                f"Only {product.stock_quantity} item(s) available in stock."
            )
            return redirect("cart")

        cart_item.quantity = new_quantity
        cart_item.save()

    messages.success(request, f"{product.name} added to cart.")
    return redirect("cart")


@login_required
def cart_view(request):
    cart = get_user_cart(request.user)
    cart_items = cart.items.select_related("product", "product__category")

    return render(request, "core/cart.html", {
        "cart": cart,
        "cart_items": cart_items,
        "cart_count": cart.total_items(),
    })


@login_required
def update_cart_item_view(request, item_id):
    cart = get_user_cart(request.user)

    cart_item = get_object_or_404(
        CartItem,
        id=item_id,
        cart=cart
    )

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "increase":
            if (
                cart_item.product.product_type == "local"
                and cart_item.quantity + 1 > cart_item.product.stock_quantity
            ):
                messages.error(
                    request,
                    f"Only {cart_item.product.stock_quantity} item(s) available in stock."
                )
            else:
                cart_item.quantity += 1
                cart_item.save()
                messages.success(request, "Cart quantity updated.")

        elif action == "decrease":
            if cart_item.quantity > 1:
                cart_item.quantity -= 1
                cart_item.save()
                messages.success(request, "Cart quantity updated.")
            else:
                cart_item.delete()
                messages.success(request, "Item removed from cart.")

    return redirect("cart")


@login_required
def remove_cart_item_view(request, item_id):
    cart = get_user_cart(request.user)

    cart_item = get_object_or_404(
        CartItem,
        id=item_id,
        cart=cart
    )

    cart_item.delete()
    messages.success(request, "Item removed from cart.")
    return redirect("cart")


@login_required
def clear_cart_view(request):
    cart = get_user_cart(request.user)
    cart.clear()
    messages.success(request, "Cart cleared.")
    return redirect("cart")


@login_required
def checkout_cart_view(request):
    cart = get_user_cart(request.user)
    cart_items = cart.items.select_related("product")

    if not cart_items.exists():
        messages.error(request, "Your cart is empty.")
        return redirect("cart")

    for item in cart_items:
        product = item.product

        if product.product_type == "local" and item.quantity > product.stock_quantity:
            messages.error(
                request,
                f"Not enough stock for {product.name}. Available: {product.stock_quantity}"
            )
            return redirect("cart")

    if request.method == "POST":
        form = OrderForm(request.POST)

        if form.is_valid():
            order = Order.objects.create(
                user=request.user,
                customer_phone=form.cleaned_data["customer_phone"],
                customer_note=form.cleaned_data["customer_note"],
            )

            for item in cart_items:
                OrderItem.objects.create(
                    order=order,
                    product=item.product,
                    product_name=item.product.name,
                    quantity=item.quantity,
                    unit_price=item.product.selling_price(),
                    product_type=item.product.product_type,
                    line_total=item.line_total(),
                )

            order.recalculate_totals()
            cart.clear()

            order_link = request.build_absolute_uri(
                reverse("order_detail", kwargs={"order_id": order.id})
            )

            item_lines = ""
            for item in order.items.all():
                item_lines += (
                    f"- {item.quantity} x {item.product_name} "
                    f"@ K{item.unit_price} = K{item.line_total}\n"
                )

            whatsapp_message = f"""
Hello, I have placed an order on China Zed Marketplace.

Order ID: #{order.id}
Customer: {request.user.username}

Items:
{item_lines}

Total Price: K{order.total_price}
Deposit Required: K{order.deposit_amount}
Balance on Arrival: K{order.balance_amount}
Phone: {order.customer_phone}
Expected Arrival: {order.estimated_arrival_start} to {order.estimated_arrival_end}

Please confirm availability and deposit instructions.

Track here:
{order_link}
"""

            whatsapp_url = f"https://wa.me/{WHATSAPP_NUMBER}?text={quote(whatsapp_message)}"
            return redirect(whatsapp_url)

    else:
        form = OrderForm()

    return render(request, "core/checkout.html", {
        "form": form,
        "cart": cart,
        "cart_items": cart_items,
        "cart_count": cart.total_items(),
    })


@login_required
def place_order_view(request, slug):
    product = get_object_or_404(
        Product,
        slug=slug,
        is_available=True
    )

    if product.product_type == "local" and product.stock_quantity <= 0:
        messages.error(request, "This product is currently out of stock.")
        return redirect("product_detail", slug=product.slug)

    if request.method == "POST":
        form = OrderForm(request.POST)

        if form.is_valid():
            order = Order.objects.create(
                user=request.user,
                customer_phone=form.cleaned_data["customer_phone"],
                customer_note=form.cleaned_data["customer_note"],
            )

            OrderItem.objects.create(
                order=order,
                product=product,
                product_name=product.name,
                quantity=1,
                unit_price=product.selling_price(),
                product_type=product.product_type,
                line_total=product.selling_price(),
            )

            order.recalculate_totals()

            order_link = request.build_absolute_uri(
                reverse("order_detail", kwargs={"order_id": order.id})
            )

            whatsapp_message = f"""
Hello, I have placed an order on China Zed Marketplace.

Order ID: #{order.id}
Customer: {request.user.username}
Product: {product.name}
Quantity: 1
Total Price: K{order.total_price}
Deposit Required: K{order.deposit_amount}
Balance on Arrival: K{order.balance_amount}
Phone: {order.customer_phone}
Expected Arrival: {order.estimated_arrival_start} to {order.estimated_arrival_end}

Please confirm availability and deposit instructions.

Track here:
{order_link}
"""

            whatsapp_url = f"https://wa.me/{WHATSAPP_NUMBER}?text={quote(whatsapp_message)}"

            return redirect(whatsapp_url)

    else:
        form = OrderForm()

    return render(request, "core/place_order.html", {
        "form": form,
        "product": product,
    })


@login_required
def order_detail_view(request, order_id):
    order = get_object_or_404(
        Order,
        id=order_id,
        user=request.user
    )

    return render(request, "core/order_detail.html", {
        "order": order,
        "cart_count": get_user_cart(request.user).total_items(),
    })


@login_required
def receipt_view(request, order_id):
    order = get_object_or_404(
        Order,
        id=order_id,
        user=request.user
    )

    allowed_statuses = ["arrived", "ready", "successful"]

    if order.status not in allowed_statuses:
        messages.error(request, "Receipt is only available once goods have arrived.")
        return redirect("profile")

    if not order.receipt_number:
        order.receipt_number = f"CZM-{order.id:05d}"
        order.save()

    return render(request, "core/receipt.html", {
        "order": order,
        "cart_count": get_user_cart(request.user).total_items(),
    })


@login_required
def receipt_pdf_view(request, order_id):
    order = get_object_or_404(
        Order,
        id=order_id,
        user=request.user
    )

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
    response["Content-Disposition"] = (
        f'attachment; filename="receipt-{order.receipt_number}.pdf"'
    )

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

        messages.error(request, "Please check the form and try again.")

    else:
        form = SupplierProductRequestForm()

    return render(request, "core/supplier_submit_product.html", {
        "form": form,
    })