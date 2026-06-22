from urllib.parse import quote
from django.utils import timezone
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import get_template
from django.urls import reverse
from django.core.mail import send_mail
from xhtml2pdf import pisa
from .forms import OrderForm, SupplierProductRequestForm, CustomUserRegistrationForm, PaymentProofForm
from .models import (
    Product,
    Order,
    OrderItem,
    Cart,
    CartItem,
    Category,
    SupplierProductRequestImage,
)
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from django.http import HttpResponse
from django.conf import settings
import os
import textwrap

WHATSAPP_NUMBER = "260969274458"
ADMIN_ORDER_EMAIL = "swiftfindzm@gmail.com"

def get_user_cart(user):
    cart, created = Cart.objects.get_or_create(user=user)
    return cart


@login_required
def upload_payment_proof_view(request, order_id):
    order = get_object_or_404(
        Order,
        id=order_id,
        user=request.user
    )

    if order.deposit_confirmed:
        messages.info(request, "Your deposit has already been confirmed.")
        return redirect("order_detail", order_id=order.id)

    if request.method == "POST":
        form = PaymentProofForm(request.POST, request.FILES, instance=order)

        if form.is_valid():
            payment_proof = form.save(commit=False)
            payment_proof.payment_proof_uploaded_at = timezone.now()
            payment_proof.save()

            messages.success(request, "Payment proof uploaded successfully. We will review it shortly.")
            return redirect("order_detail", order_id=order.id)
    else:
        form = PaymentProofForm(instance=order)

    return render(request, "core/upload_payment_proof.html", {
        "form": form,
        "order": order,
        "cart_count": get_user_cart(request.user).total_items(),
    })

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


from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib import messages
from django.core.mail import send_mail
from django_ratelimit.decorators import ratelimit

@ratelimit(key="ip", rate="3/h", block=True)
def register_view(request):

    # HONEYPOT CHECK
    if request.method == "POST":
        if request.POST.get("website"):
            return redirect("home")

        form = CustomUserRegistrationForm(request.POST)

        if form.is_valid():
            user = form.save()

            if user.email:
                send_mail(
                    subject="Welcome to China to Zambia Marketplace",
                    message=f"""
Hello {user.username},

Welcome to China to Zambia Marketplace.

Thank you for registering with us.

You can now browse products, place orders, track your orders, and contact us easily.

Regards,
China to Zambia Team
""",
                    from_email=None,
                    recipient_list=[user.email],
                    fail_silently=True,
                )

            login(request, user)
            messages.success(request, "Account created successfully.")
            return redirect("home")

    else:
        form = CustomUserRegistrationForm()

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

            if request.user.email:
                send_mail(
                    subject=f"Order Received - #{order.id}",
                    message=f"""
Hello {request.user.username},

Thank you for placing your order on ChinaZed.

Order ID: #{order.id}

Items:
{item_lines}

Total Price: K{order.total_price}
Deposit Required: K{order.deposit_amount}
Balance on Arrival: K{order.balance_amount}

Phone: {order.customer_phone}
Expected Arrival: {order.estimated_arrival_start} to {order.estimated_arrival_end}

Track your order here:
{order_link}

We will contact you shortly to confirm availability and deposit instructions.

Regards,
ChinaZed Team
""",
                    from_email=None,
                    recipient_list=[request.user.email],
                    fail_silently=True,
                )

            send_mail(
                subject=f"New Order Placed - #{order.id}",
                message=f"""
New order received on ChinaZed.

Order ID: #{order.id}
Customer: {request.user.username}
Customer Email: {request.user.email}
Customer Phone: {order.customer_phone}

Items:
{item_lines}

Total Price: K{order.total_price}
Deposit Required: K{order.deposit_amount}
Balance on Arrival: K{order.balance_amount}

Expected Arrival:
{order.estimated_arrival_start} to {order.estimated_arrival_end}

Customer Note:
{order.customer_note}

Order Link:
{order_link}
""",
                from_email=None,
                recipient_list=[ADMIN_ORDER_EMAIL],
                fail_silently=True,
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

            item_lines = (
                f"- 1 x {product.name} "
                f"@ K{product.selling_price()} = K{product.selling_price()}\n"
            )

            if request.user.email:
                send_mail(
                    subject=f"Order Received - #{order.id}",
                    message=f"""
Hello {request.user.username},

Thank you for placing your order on ChinaZed.

Order ID: #{order.id}

Product: {product.name}
Quantity: 1

Total Price: K{order.total_price}
Deposit Required: K{order.deposit_amount}
Balance on Arrival: K{order.balance_amount}

Phone: {order.customer_phone}
Expected Arrival: {order.estimated_arrival_start} to {order.estimated_arrival_end}

Track your order here:
{order_link}

We will contact you shortly to confirm availability and deposit instructions.

Regards,
ChinaZed Team
""",
                    from_email=None,
                    recipient_list=[request.user.email],
                    fail_silently=True,
                )

            send_mail(
                subject=f"New Order Placed - #{order.id}",
                message=f"""
New order received on ChinaZed.

Order ID: #{order.id}
Customer: {request.user.username}
Customer Email: {request.user.email}
Customer Phone: {order.customer_phone}

Items:
{item_lines}

Total Price: K{order.total_price}
Deposit Required: K{order.deposit_amount}
Balance on Arrival: K{order.balance_amount}

Expected Arrival:
{order.estimated_arrival_start} to {order.estimated_arrival_end}

Customer Note:
{order.customer_note}

Order Link:
{order_link}
""",
                from_email=None,
                recipient_list=[ADMIN_ORDER_EMAIL],
                fail_silently=True,
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
    try:
        order = Order.objects.get(
            id=order_id,
            user=request.user
        )
    except Order.DoesNotExist:
        messages.error(request, "You are not allowed to view that order.")
        return redirect("profile")

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
        form = SupplierProductRequestForm(
            request.POST,
            request.FILES
        )

        if form.is_valid():
            supplier_request = form.save(commit=False)

            # Set preview image from first uploaded image later
            uploaded_images = request.FILES.getlist("images")

            # fallback single image
            if not uploaded_images and request.FILES.get("image"):
                supplier_request.image = request.FILES.get("image")

            supplier_request.save()

            # Save multiple images
            for index, img in enumerate(uploaded_images):

                SupplierProductRequestImage.objects.create(
                    supplier_request=supplier_request,
                    image=img
                )

                # first image becomes cover image
                if index == 0 and not supplier_request.image:
                    supplier_request.image = img
                    supplier_request.save()

            messages.success(
                request,
                "Your product was submitted successfully and is awaiting review."
            )

            return redirect("supplier_submit_product")

        else:
            messages.error(
                request,
                "Please correct the errors below."
            )

    else:
        form = SupplierProductRequestForm()

    return render(
        request,
        "core/supplier_submit_product.html",
        {
            "form": form,
        }
    )

import textwrap
from io import BytesIO
import qrcode

from django.shortcuts import get_object_or_404
from django.http import HttpResponse
from django.urls import reverse
from django.core.cache import cache
from django.views.decorators.http import require_GET
from PIL import Image, ImageDraw, ImageFont

from .models import Product # Adjust this import path to match your project structure


def get_font(font_path, size, bold=False):
    """
    Attempts to load a font from the specified path.
    If it fails, searches common system fallbacks before defaulting.
    """
    try:
        return ImageFont.truetype(font_path, size)
    except (IOError, OSError):
        # Common fallbacks across Linux, macOS, and Windows
        fallbacks = [
            "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
            "Arial Bold.ttf" if bold else "Arial.ttf",
            "Helvetica-Bold" if bold else "Helvetica",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
        for font_name in fallbacks:
            try:
                return ImageFont.truetype(font_name, size)
            except (IOError, OSError):
                continue
        # Hard fallback to PIL's default (Note: default font does not support custom sizes)
        return ImageFont.load_default()


import logging
import textwrap
from io import BytesIO
import qrcode

from django.conf import settings
from django.core.files.storage import default_storage
from django.http import HttpResponse, Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_GET
from PIL import Image, ImageDraw, ImageFont

from .models import Product  # Adjust the import path to match your project layout

# Configure logger for standard Django error reporting
logger = logging.getLogger(__name__)


def load_system_font(font_name_or_path, size):
    """
    Standard font loader with a cascading fallback system.
    Tries the requested path first, then searches common system locations,
    and falls back to standard default fonts to prevent OS-level crashes.
    """
    try:
        return ImageFont.truetype(font_name_or_path, size)
    except (IOError, OSError):
        # List of standard fonts available across Windows, macOS, Linux, and Docker
        fallbacks = [
            "DejaVuSans-Bold.ttf" if "Bold" in font_name_or_path else "DejaVuSans.ttf",
            "Arial Bold.ttf" if "Bold" in font_name_or_path else "Arial.ttf",
            "Helvetica-Bold" if "Bold" in font_name_or_path else "Helvetica",
            "LiberationSans-Bold.ttf" if "Bold" in font_name_or_path else "LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "arial.ttf",
        ]

        for fallback in fallbacks:
            try:
                return ImageFont.truetype(fallback, size)
            except (IOError, OSError):
                continue

        # Return standard default system font if all custom TrueType fonts fail
        return ImageFont.load_default()


import logging
import textwrap
from io import BytesIO
from decimal import Decimal, InvalidOperation

import qrcode
from PIL import Image, ImageDraw, ImageFont

from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_GET

from .models import Product

logger = logging.getLogger(__name__)


# =========================
# FONT HELPERS
# =========================

def load_system_font(font_name_or_path, size):
    try:
        return ImageFont.truetype(font_name_or_path, size)
    except (IOError, OSError):
        fallbacks = [
            "DejaVuSans-Bold.ttf" if "Bold" in font_name_or_path else "DejaVuSans.ttf",
            "Arial Bold.ttf" if "Bold" in font_name_or_path else "Arial.ttf",
            "LiberationSans-Bold.ttf" if "Bold" in font_name_or_path else "LiberationSans-Regular.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if "Bold" in font_name_or_path else
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "arial.ttf",
        ]

        for fallback in fallbacks:
            try:
                return ImageFont.truetype(fallback, size)
            except (IOError, OSError):
                continue

        return ImageFont.load_default()


def safe_decimal(value, default="0"):
    try:
        if callable(value):
            value = value()

        if value is None:
            return Decimal(default)

        cleaned = str(value).replace(",", "").replace("K", "").strip()
        return Decimal(cleaned)

    except (InvalidOperation, ValueError, TypeError):
        return Decimal(default)


def format_currency(value):
    amount = safe_decimal(value)

    if amount == amount.to_integral():
        return f"{int(amount):,}"

    return f"{amount:,.2f}"


def safe_text(value, default=""):
    try:
        if callable(value):
            value = value()

        if value is None:
            return default

        return str(value)

    except Exception:
        return default


def truncate_to_width(draw, text, font, max_width):
    text = safe_text(text)

    if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
        return text

    while len(text) > 3:
        shortened = text[:-3].rstrip() + "..."
        if draw.textbbox((0, 0), shortened, font=font)[2] <= max_width:
            return shortened
        text = text[:-1]

    return "..."


def draw_centered_text(draw, box, text, font, fill):
    x1, y1, x2, y2 = box
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    x = x1 + ((x2 - x1 - tw) // 2)
    y = y1 + ((y2 - y1 - th) // 2)

    draw.text((x, y), text, font=font, fill=fill)


def draw_wrapped_text(draw, text, x, y, font, fill, max_width, line_gap, max_lines):
    words = safe_text(text).split()
    lines = []
    current = ""

    for word in words:
        test_line = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test_line, font=font)

        if bbox[2] - bbox[0] <= max_width:
            current = test_line
        else:
            if current:
                lines.append(current)
            current = word

        if len(lines) >= max_lines:
            break

    if current and len(lines) < max_lines:
        lines.append(current)

    if len(lines) > max_lines:
        lines = lines[:max_lines]

    if len(words) > len(" ".join(lines).split()) and lines:
        lines[-1] = truncate_to_width(draw, lines[-1] + "...", font, max_width)

    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += line_gap

    return y


def get_product_price(product, field_name, fallback="0"):
    value = getattr(product, field_name, fallback)
    return format_currency(value)


def get_product_value(product, field_name, fallback=""):
    value = getattr(product, field_name, fallback)
    return safe_text(value, fallback)


# =========================
# MAIN VIEW
# =========================

@require_GET
def save_product_image_view(request, slug):
    """
    Generates a clean marketplace poster for a product.

    Recommended output:
    - JPEG
    - 2160 x 3200
    - easier to share on WhatsApp
    - lighter than huge PNG files
    """

    product = get_object_or_404(Product, slug=slug, is_available=True)

    # S=2 is high quality but safer for PythonAnywhere.
    # Use S=4 only when you want very large print-quality images.
    S = 2

    W, H = 1080 * S, 1600 * S

    def p(value):
        return int(value * S)

    poster = Image.new("RGB", (W, H), "#F9FAFB")
    draw = ImageDraw.Draw(poster)

    # =========================
    # COLORS
    # =========================

    ORANGE = "#FF5A00"
    ORANGE_LIGHT = "#FFF3EA"
    RED = "#E5141A"
    DARK = "#111827"
    GREY = "#6B7280"
    LIGHT_GREY = "#E5E7EB"
    WHITE = "#FFFFFF"
    GREEN = "#16A34A"
    BORDER = "#E5E7EB"
    YELLOW = "#FACC15"

    # =========================
    # FONTS
    # =========================

    regular_font = "DejaVuSans.ttf"
    bold_font = "DejaVuSans-Bold.ttf"

    tiny = load_system_font(regular_font, p(18))
    small = load_system_font(regular_font, p(22))
    font = load_system_font(regular_font, p(28))
    bold_small = load_system_font(bold_font, p(24))
    bold = load_system_font(bold_font, p(30))
    big = load_system_font(bold_font, p(48))
    title_font = load_system_font(bold_font, p(50))
    huge = load_system_font(bold_font, p(74))
    brand_font = load_system_font(bold_font, p(58))

    # =========================
    # PRODUCT URL
    # =========================

    product_url = request.build_absolute_uri(
        reverse("product_detail", kwargs={"slug": product.slug})
    )

    # =========================
    # HEADER
    # =========================

    draw.rectangle((0, 0, W, p(170)), fill=ORANGE)

    draw.rounded_rectangle(
        (p(45), p(42), p(135), p(132)),
        radius=p(18),
        fill=WHITE
    )

    draw_centered_text(
        draw,
        (p(45), p(42), p(135), p(132)),
        "CZ",
        bold,
        ORANGE
    )

    draw.text((p(155), p(42)), "China Zed", font=brand_font, fill=WHITE)
    draw.text((p(160), p(108)), "M A R K E T P L A C E", font=small, fill=WHITE)

    header_badges = [
        "TRUSTED PLATFORM",
        "SECURE ORDERS",
        "RELIABLE SUPPORT",
    ]

    badge_y = p(34)

    for badge in header_badges:
        draw.rounded_rectangle(
            (p(690), badge_y, p(1010), badge_y + p(34)),
            radius=p(8),
            fill="#E04D00"
        )
        draw_centered_text(
            draw,
            (p(690), badge_y, p(1010), badge_y + p(34)),
            badge,
            tiny,
            WHITE
        )
        badge_y += p(42)

    # =========================
    # MAIN CARD
    # =========================

    draw.rounded_rectangle(
        (p(48), p(190), p(1048), p(1390)),
        radius=p(36),
        fill="#D1D5DB"
    )

    draw.rounded_rectangle(
        (p(40), p(182), p(1040), p(1380)),
        radius=p(36),
        fill=WHITE
    )

    # =========================
    # PRODUCT IMAGE
    # =========================

    img_x, img_y = p(65), p(240)
    img_w, img_h = p(450), p(560)

    draw.rounded_rectangle(
        (img_x - p(6), img_y - p(6), img_x + img_w + p(6), img_y + img_h + p(6)),
        radius=p(22),
        fill="#F3F4F6"
    )

    if product.image:
        try:
            with product.image.open("rb") as img_file:
                img = Image.open(img_file).convert("RGBA")

                src_w, src_h = img.size
                scale = max(img_w / src_w, img_h / src_h)

                new_w = int(src_w * scale)
                new_h = int(src_h * scale)

                img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

                crop_x = max((new_w - img_w) // 2, 0)
                crop_y = max((new_h - img_h) // 2, 0)

                img = img.crop((crop_x, crop_y, crop_x + img_w, crop_y + img_h))

                bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
                bg.paste(img, mask=img.split()[3])

                poster.paste(bg.convert("RGB"), (img_x, img_y))

        except Exception as exc:
            logger.exception("Failed to generate product poster image: %s", exc)

            draw.rounded_rectangle(
                (img_x, img_y, img_x + img_w, img_y + img_h),
                radius=p(18),
                fill=LIGHT_GREY
            )
            draw_centered_text(
                draw,
                (img_x, img_y, img_x + img_w, img_y + img_h),
                "No Image",
                bold,
                GREY
            )
    else:
        draw.rounded_rectangle(
            (img_x, img_y, img_x + img_w, img_y + img_h),
            radius=p(18),
            fill=LIGHT_GREY
        )
        draw_centered_text(
            draw,
            (img_x, img_y, img_x + img_w, img_y + img_h),
            "No Image",
            bold,
            GREY
        )

    draw.ellipse(
        (p(115), p(785), p(475), p(825)),
        fill="#E5E7EB"
    )

    # =========================
    # QUALITY BADGE
    # =========================

    bx, by = p(70), p(665)

    draw.ellipse(
        (bx, by, bx + p(155), by + p(155)),
        fill=DARK,
        outline=YELLOW,
        width=p(7)
    )

    draw_centered_text(
        draw,
        (bx, by + p(14), bx + p(155), by + p(50)),
        "★★★★★",
        tiny,
        YELLOW
    )

    draw_centered_text(
        draw,
        (bx, by + p(50), bx + p(155), by + p(88)),
        "QUALITY",
        bold_small,
        YELLOW
    )

    draw_centered_text(
        draw,
        (bx, by + p(88), bx + p(155), by + p(128)),
        "CHECKED",
        small,
        WHITE
    )

    # =========================
    # PRODUCT TYPE BADGE
    # =========================

    product_type = get_product_value(product, "product_type", "preorder")

    if product_type == "preorder":
        badge_text = "PRE-ORDER FROM CHINA"
        badge_color = RED
    else:
        badge_text = "AVAILABLE IN ZAMBIA"
        badge_color = GREEN

    draw.rounded_rectangle(
        (p(545), p(220), p(940), p(270)),
        radius=p(12),
        fill=badge_color
    )

    draw_centered_text(
        draw,
        (p(545), p(220), p(940), p(270)),
        badge_text,
        small,
        WHITE
    )

    # =========================
    # PRODUCT TITLE
    # =========================

    product_name = get_product_value(product, "name", "Product")

    draw_wrapped_text(
        draw=draw,
        text=product_name,
        x=p(545),
        y=p(302),
        font=title_font,
        fill=DARK,
        max_width=p(455),
        line_gap=p(58),
        max_lines=3,
    )

    # =========================
    # PRICE BOX
    # =========================

    price_box_top = p(520)

    draw.rounded_rectangle(
        (p(515), price_box_top, p(1020), price_box_top + p(255)),
        radius=p(22),
        outline=ORANGE,
        width=p(3),
        fill=ORANGE_LIGHT
    )

    draw.rounded_rectangle(
        (p(680), price_box_top + p(14), p(875), price_box_top + p(56)),
        radius=p(10),
        fill=ORANGE
    )

    draw_centered_text(
        draw,
        (p(680), price_box_top + p(14), p(875), price_box_top + p(56)),
        "TOTAL PRICE",
        small,
        WHITE
    )

    price_val = get_product_price(product, "selling_price")
    deposit_val = get_product_price(product, "deposit_amount")
    balance_val = get_product_price(product, "balance_amount")

    price_text = f"K{price_val}"

    price_text = truncate_to_width(
        draw,
        price_text,
        huge,
        p(455)
    )

    draw.text(
        (p(545), price_box_top + p(72)),
        price_text,
        font=huge,
        fill=RED
    )

    divider_y = price_box_top + p(172)

    draw.line(
        (p(545), divider_y, p(985), divider_y),
        fill="#F3C2A3",
        width=p(2)
    )

    draw.text((p(570), divider_y + p(18)), "DEPOSIT", font=small, fill=DARK)
    draw.text((p(570), divider_y + p(48)), f"K{deposit_val}", font=bold, fill=RED)

    draw.line(
        (p(775), divider_y + p(10), p(775), divider_y + p(85)),
        fill="#F3C2A3",
        width=p(2)
    )

    draw.text((p(805), divider_y + p(18)), "BALANCE", font=small, fill=DARK)
    draw.text((p(805), divider_y + p(48)), f"K{balance_val}", font=bold, fill=RED)

    # =========================
    # PRODUCT DETAILS
    # =========================

    detail_y = p(815)

    sku = get_product_value(product, "sku", "N/A")[:28]

    stock_status = getattr(product, "stock_status", "Available")
    stock_status = safe_text(stock_status, "Available")

    delivery_range = getattr(product, "delivery_range", "Ask for ETA")
    delivery_range = safe_text(delivery_range, "Ask for ETA")

    if hasattr(product, "get_product_type_display"):
        product_type_display = safe_text(product.get_product_type_display(), product_type)
    else:
        product_type_display = product_type.replace("_", " ").title()

    condition = get_product_value(product, "condition", "Brand New")

    details = [
        ("SKU:", sku),
        ("TYPE:", product_type_display),
        ("STOCK:", stock_status),
        ("CONDITION:", condition),
        ("DELIVERY:", delivery_range),
    ]

    for label, value in details:
        draw.text((p(545), detail_y), label, font=bold, fill=DARK)

        value = truncate_to_width(
            draw,
            value,
            font,
            p(270)
        )

        draw.text((p(735), detail_y), value, font=font, fill=DARK)

        draw.line(
            (p(545), detail_y + p(46), p(1000), detail_y + p(46)),
            fill=BORDER,
            width=p(1)
        )

        detail_y += p(60)

    # =========================
    # TRUST SECTION
    # =========================

    trust_top = p(1060)

    draw.rounded_rectangle(
        (p(55), trust_top, p(1025), trust_top + p(155)),
        radius=p(22),
        fill=WHITE,
        outline=BORDER,
        width=p(2)
    )

    trust_badges = [
        ("SECURE", "Safe Orders", "Trusted process"),
        ("GUARANTEE", "Pre-order Care", "We source carefully"),
        ("DELIVERY", "Zambia Delivery", "Clear ETA guidance"),
        ("SUPPORT", "WhatsApp Help", "Ask before buying"),
    ]

    tx = p(75)

    for label, heading, desc in trust_badges:
        draw.rounded_rectangle(
            (tx, trust_top + p(14), tx + p(205), trust_top + p(52)),
            radius=p(8),
            fill=ORANGE
        )

        draw_centered_text(
            draw,
            (tx, trust_top + p(14), tx + p(205), trust_top + p(52)),
            label,
            tiny,
            WHITE
        )

        draw.text((tx, trust_top + p(68)), heading, font=small, fill=DARK)
        draw.text((tx, trust_top + p(105)), desc, font=tiny, fill=GREY)

        tx += p(240)

    # =========================
    # WHATSAPP SECTION
    # =========================

    whatsapp_number = "+260 969 274 458"

    wa_y = p(1240)

    draw.rounded_rectangle(
        (p(55), wa_y, p(810), wa_y + p(170)),
        radius=p(24),
        fill=GREEN
    )

    draw.text(
        (p(78), wa_y + p(22)),
        "Order or Ask on WhatsApp",
        font=bold,
        fill=WHITE
    )

    draw.line(
        (p(78), wa_y + p(72), p(790), wa_y + p(72)),
        fill="#15803D",
        width=p(2)
    )

    draw.text(
        (p(78), wa_y + p(86)),
        whatsapp_number,
        font=big,
        fill=WHITE
    )

    draw.text(
        (p(78), wa_y + p(144)),
        "Scan the QR code to view product",
        font=small,
        fill="#BBF7D0"
    )

    # =========================
    # QR CODE
    # =========================

    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=4 * S,
        border=2,
    )

    qr.add_data(product_url)
    qr.make(fit=True)

    qr_img = qr.make_image(
        fill_color="black",
        back_color="white"
    ).convert("RGB")

    qr_size = p(165)
    qr_img = qr_img.resize((qr_size, qr_size), Image.Resampling.NEAREST)

    qr_x = p(840)
    qr_y = p(1238)

    draw.rounded_rectangle(
        (
            qr_x - p(12),
            qr_y - p(12),
            qr_x + qr_size + p(12),
            qr_y + qr_size + p(12),
        ),
        radius=p(12),
        fill=WHITE,
        outline=BORDER,
        width=p(2)
    )

    poster.paste(qr_img, (qr_x, qr_y))

    draw_centered_text(
        draw,
        (
            qr_x - p(20),
            qr_y + qr_size + p(10),
            qr_x + qr_size + p(20),
            qr_y + qr_size + p(45),
        ),
        "Scan to View",
        tiny,
        DARK
    )

    # =========================
    # FOOTER
    # =========================

    footer_top = p(1440)

    draw.rectangle(
        (0, footer_top, W, H),
        fill=RED
    )

    draw.text(
        (p(80), p(1460)),
        "TRUSTED BY CUSTOMERS IN ZAMBIA",
        font=small,
        fill=WHITE
    )

    draw.text(
        (p(455), p(1458)),
        "★★★★★",
        font=bold,
        fill=YELLOW
    )

    draw.text(
        (p(740), p(1454)),
        "China Zed",
        font=bold,
        fill=WHITE
    )

    draw.text(
        (p(758), p(1494)),
        "MARKETPLACE",
        font=tiny,
        fill=WHITE
    )

    draw.text(
        (p(80), p(1530)),
        "Fast sourcing • Zambia delivery • WhatsApp support",
        font=tiny,
        fill=WHITE
    )

    # =========================
    # OUTPUT
    # =========================

    buffer = BytesIO()

    # JPEG is better for WhatsApp and faster downloads.
    poster.save(
        buffer,
        format="JPEG",
        quality=95,
        optimize=True,
        progressive=True
    )

    buffer.seek(0)

    response = HttpResponse(buffer, content_type="image/jpeg")
    response["Content-Disposition"] = (
        f'attachment; filename="{product.slug}-poster.jpg"'
    )

    return response


