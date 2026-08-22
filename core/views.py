import json
import requests
from django.conf import settings
from django.utils import timezone
from django.contrib import messages
from django.contrib.auth import get_user_model, logout
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.template.loader import get_template
from django.urls import reverse
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.core.mail import send_mail
from django.views.decorators.http import require_POST
from django_ratelimit.decorators import ratelimit
from xhtml2pdf import pisa
from .forms import (
    CustomerProductRequestForm,
    OrderForm,
    SupplierProductRequestForm,
    CustomUserRegistrationForm,
    PaymentProofForm,
)
from .marketplace_importer import ImportFailure, import_marketplace_product
from .utils import with_display_annotations, apply_sort
from .models import (
    Product,
    ProductReview,
    CustomerProductRequest,
    Order,
    OrderItem,
    Cart,
    CartItem,
    Category,
    SupplierProductRequest,
    SupplierProductRequestImage,
    money,
)
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from django.http import HttpResponse
from django.conf import settings
import os
import textwrap
import re
import html as html_lib
from urllib.parse import urlparse
from datetime import timedelta

WHATSAPP_NUMBER = "260766491002"
ADMIN_ORDER_EMAIL = "swiftfindzm@gmail.com"


AI_ASSISTANT_SYSTEM_PROMPT = """
You are the ChinaZed Marketplace customer assistant for buyers in Zambia.
Answer clearly and politely. Keep replies short and practical.

Business rules:
- China pre-orders use a 35% deposit.
- Balance is paid when the order arrives and is ready for pickup or local delivery.
- Link-imported China pre-orders have an estimated delivery window of 14 to 60 days.
- After the first deposit, requested size, color, and quantity are verified within two days.
- If the buyer declines unavailable options before purchase, the full deposit is refundable.
- Customers can request a product quote from Alibaba, Taobao, Temu, 1688, Shein, or another supplier.
- If an item is unavailable, ChinaZed helps find an alternative or adjusts the order.
- Refunds or changes follow the order policy.
- Do not promise exact availability, final pricing, or delivery dates without staff confirmation.
- If a customer needs account-specific changes, payment verification, refund approval, or urgent support, tell them staff will review it.
"""


def fallback_assistant_reply(message):
    text = message.lower()

    if "deposit" in text or "pay" in text:
        return "ChinaZed pre-orders start with a 35% deposit. The balance is paid when your order arrives and is ready for pickup or local delivery."

    if "delivery" in text or "arrive" in text or "shipping" in text:
        return "Link-imported China pre-orders have an estimated delivery window of 14 to 60 days. Size, color, and quantity are verified within two days after the deposit."

    if "request" in text or "quote" in text or "alibaba" in text or "taobao" in text or "temu" in text or "1688" in text or "shein" in text:
        return "You can request any product from China by sending the product link through the Request Product page. ChinaZed will check availability, shipping, and quote the Zambia price."

    if "refund" in text or "unavailable" in text or "change" in text:
        return "If the requested size, color, or quantity is unavailable, ChinaZed will send the available options. If you decide not to continue before purchase, your deposit is refunded in full."

    return "I can help with ChinaZed deposits, delivery, product requests, order tracking, balances, and refunds. What would you like to know?"


def assistant_view(request):
    cart_count = 0
    if request.user.is_authenticated:
        cart_count = get_user_cart(request.user).total_items()

    return render(request, "core/assistant.html", {
        "cart_count": cart_count,
        "initial_message": request.GET.get("message", "").strip(),
    })


@require_POST
@ratelimit(key="ip", rate="30/h", method="POST", block=True)
def assistant_chat_view(request):
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        payload = request.POST

    message = (payload.get("message") or "").strip()

    if not message:
        return JsonResponse({
            "reply": "Please type your question so I can help."
        })

    context_lines = []
    if request.user.is_authenticated:
        recent_orders = Order.objects.filter(user=request.user).order_by("-order_date")[:3]
        for order in recent_orders:
            context_lines.append(
                f"Order #{order.id}: status {order.get_status_display()}, total K{order.total_price}, "
                f"deposit K{order.deposit_amount}, balance K{order.balance_amount}."
            )

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        return JsonResponse({"reply": fallback_assistant_reply(message)})

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                "messages": [
                    {"role": "system", "content": AI_ASSISTANT_SYSTEM_PROMPT},
                    {"role": "system", "content": "\n".join(context_lines) if context_lines else "No signed-in order context."},
                    {"role": "user", "content": message},
                ],
                "temperature": 0.3,
                "max_tokens": 240,
            },
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        reply = data["choices"][0]["message"]["content"].strip()
    except Exception:
        reply = fallback_assistant_reply(message)

    return JsonResponse({"reply": reply})


@login_required(login_url="login")
@require_POST
@ratelimit(key="user", rate="20/h", method="POST", block=True)
def marketplace_import_preview_view(request):
    if not is_approved_supplier(request.user):
        return JsonResponse({"error": "Approved supplier access is required.", "code": "forbidden"}, status=403)
    share_text = (request.POST.get("share_text") or "").strip()
    try:
        result = import_marketplace_product(
            share_text,
            owner_id=request.user.pk,
            translate=_translate_product_text,
        )
        return JsonResponse(result.as_dict())
    except ImportFailure as exc:
        return JsonResponse({"error": exc.message, "code": exc.code}, status=exc.status)


def taobao_import_preview_view(request):
    """Backward-compatible endpoint; the shared importer auto-detects the marketplace."""
    return marketplace_import_preview_view(request)

def service_worker_view(request):
    response = render(
        request,
        "core/service-worker.js",
        content_type="application/javascript",
    )
    response["Service-Worker-Allowed"] = "/"
    return response


def get_user_cart(user):
    cart, created = Cart.objects.get_or_create(user=user)
    return cart


def send_activation_email(request, user):
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = default_token_generator.make_token(user)
    activation_link = request.build_absolute_uri(
        reverse("activate_account", kwargs={"uidb64": uid, "token": token})
    )

    send_mail(
        subject="Activate your ChinaZed account",
        message=f"""
Hello {user.username},

Thank you for registering with ChinaZed.

Please click the link below to verify your email and activate your account:

{activation_link}

If you did not create this account, you can ignore this email.

Regards,
ChinaZed Team
""",
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )

    return activation_link


@login_required(login_url="login")
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
    sort = request.GET.get("sort", "").strip()

    products = Product.objects.filter(is_available=True).order_by("-created_at")
    categories = Category.objects.all().order_by("name")

    featured_products = with_display_annotations(Product.objects.filter(
        is_available=True,
        is_featured=True
    )).order_by("-created_at")[:8]

    local_products = with_display_annotations(Product.objects.filter(
        is_available=True,
        product_type="local",
        stock_quantity__gt=0
    )).order_by("-created_at")[:10]

    preorder_products = with_display_annotations(Product.objects.filter(
        is_available=True,
        product_type="preorder"
    )).order_by("-created_at")[:10]

    testimonials = ProductReview.objects.filter(
        is_approved=True
    ).select_related("product", "user").order_by("-created_at")[:3]

    if query:
        products = products.filter(name__icontains=query)

    if category_id:
        products = products.filter(category_id=category_id)

    if product_type in ["local", "preorder"]:
        products = products.filter(product_type=product_type)

    products = with_display_annotations(products)
    products = apply_sort(products, sort) if sort else products.order_by("-created_at")

    cart_count = 0
    if request.user.is_authenticated:
        cart_count = get_user_cart(request.user).total_items()

    return render(request, "core/home.html", {
        "products": products,
        "categories": categories,
        "query": query,
        "category_id": category_id,
        "product_type": product_type,
        "sort": sort,
        "featured_products": featured_products,
        "local_products": local_products,
        "preorder_products": preorder_products,
        "testimonials": testimonials,
        "cart_count": cart_count,
    })


@ratelimit(key="ip", rate="60/m", method="GET", block=True)
def search_suggestions_view(request):
    query = request.GET.get("q", "").strip()
    suggestions = []
    if len(query) >= 2:
        suggestions = Product.objects.filter(
            is_available=True, name__icontains=query
        ).order_by("-is_featured", "-created_at")[:6]

    return render(request, "core/components/_search_suggestions.html", {
        "suggestions": suggestions,
        "query": query,
    })


def home_recommendations_view(request):
    raw_ids = request.GET.get("categories", "")
    category_ids = [c for c in raw_ids.split(",") if c.strip().isdigit()]

    products = []
    if category_ids:
        products = with_display_annotations(Product.objects.filter(
            is_available=True, category_id__in=category_ids
        )).order_by("-is_featured", "-created_at")[:10]

    return render(request, "core/components/_product_grid.html", {
        "products": products,
    })


def about(request):
    cart_count = 0
    if request.user.is_authenticated:
        cart_count = get_user_cart(request.user).total_items()

    return render(request, "core/about.html", {
        "cart_count": cart_count,
    })


def terms(request):
    return render(request, "core/terms.html")


def privacy(request):
    return render(request, "core/privacy.html")


def faq(request):
    return render(request, "core/faq.html")


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


@login_required(login_url="login")
def request_product_view(request):
    if request.method == "POST":
        form = CustomerProductRequestForm(request.POST, request.FILES)

        if form.is_valid():
            product_request = form.save(commit=False)
            product_request.user = request.user
            product_request.save()
            messages.success(request, "Product request submitted. We will review the link and prepare a quote.")
            return redirect("profile")
    else:
        form = CustomerProductRequestForm()

    return render(request, "core/request_product.html", {
        "form": form,
        "cart_count": get_user_cart(request.user).total_items(),
    })


from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.mail import send_mail


class ChinaZedLoginView(LoginView):
    template_name = "core/login.html"

    def get_success_url(self):
        return reverse("profile")

    def form_invalid(self, form):
        username = self.request.POST.get("username", "").strip()

        if username:
            User = get_user_model()
            user = User.objects.filter(username__iexact=username, is_active=False).first()

            if user:
                self.request.session["pending_activation_email"] = user.email
                messages.error(
                    self.request,
                    "Please verify your email before logging in. Check your inbox or spam folder, or resend the activation email."
                )
                return redirect("registration_pending")

        return super().form_invalid(form)

@ratelimit(key="ip", rate="10/h", method="POST", block=True)
def register_view(request):

    # HONEYPOT CHECK
    if request.method == "POST":
        if request.POST.get("website"):
            return redirect("home")

        form = CustomUserRegistrationForm(request.POST)

        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False
            user.save()

            try:
                send_activation_email(request, user)
            except Exception:
                user.delete()
                messages.error(request, "We could not send the verification email. Please check the address or try again later.")
                return redirect("register")

            request.session["pending_activation_email"] = user.email
            return redirect("registration_pending")

    else:
        form = CustomUserRegistrationForm()

    return render(request, "core/register.html", {
        "form": form,
    })


def registration_pending_view(request):
    email = request.session.get("pending_activation_email", "")
    dev_activation_link = ""

    if settings.DEBUG and settings.EMAIL_BACKEND.endswith(".console.EmailBackend") and email:
        User = get_user_model()
        user = User.objects.filter(email__iexact=email, is_active=False).first()

        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            dev_activation_link = request.build_absolute_uri(
                reverse("activate_account", kwargs={"uidb64": uid, "token": token})
            )

    return render(request, "core/registration_pending.html", {
        "email": email,
        "dev_activation_link": dev_activation_link,
    })


@ratelimit(key="post:email", rate="3/h", method="POST", block=True)
def resend_activation_view(request):
    if request.method != "POST":
        return redirect("register")

    email = request.POST.get("email", "").strip().lower()

    if not email:
        messages.error(request, "Please enter the email address you used to register.")
        return redirect("registration_pending")

    User = get_user_model()
    user = User.objects.filter(email__iexact=email, is_active=False).first()

    if user:
        send_activation_email(request, user)
        request.session["pending_activation_email"] = user.email

    messages.success(request, "If that email has an unverified account, we sent a new activation link. Please check inbox and spam.")
    return redirect("registration_pending")


def activate_account_view(request, uidb64, token):
    User = get_user_model()

    try:
        uid = force_str(urlsafe_base64_decode(uidb64))
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        user = None

    if user is not None and default_token_generator.check_token(user, token):
        user.is_active = True
        user.save(update_fields=["is_active"])
        messages.success(request, "Your email has been verified. You can now log in.")
        return redirect("login")

    return render(request, "core/activation_invalid.html")

def logout_view(request):
    logout(request)
    return redirect("home")


@login_required(login_url="login")
def profile_view(request):
    orders = (
        Order.objects.filter(user=request.user)
        .prefetch_related("items__product")
        .order_by("-order_date")
    )

    successful_orders = orders.filter(status="successful")
    cancelled_orders = orders.filter(status="cancelled")
    product_requests = CustomerProductRequest.objects.filter(
        user=request.user,
        is_deleted=False,
    ).order_by("-created_at")

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
        "product_requests": product_requests,
        "cart_count": cart_count,
        "vapid_public_key": settings.WEBPUSH_SETTINGS["VAPID_PUBLIC_KEY"],
    })


@login_required(login_url="login")
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

    requested_size = (request.POST.get("size") or "").strip()
    requested_color = (request.POST.get("color") or "").strip()
    if requested_size and requested_size not in product.size_option_list():
        messages.error(request, "Please choose a valid size.")
        return redirect("product_detail", slug=product.slug)
    if requested_color and requested_color not in product.color_option_list():
        messages.error(request, "Please choose a valid color.")
        return redirect("product_detail", slug=product.slug)

    if product.product_type == "local" and product.stock_quantity <= 0:
        messages.error(request, "This product is currently out of stock.")
        return redirect("product_detail", slug=product.slug)

    cart = get_user_cart(request.user)

    cart_item, created = CartItem.objects.get_or_create(
        cart=cart,
        product=product,
        requested_size=requested_size,
        requested_color=requested_color,
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


@login_required(login_url="login")
def cart_view(request):
    cart = get_user_cart(request.user)
    cart_items = cart.items.select_related("product", "product__category")

    template = "core/cart.html"
    if request.headers.get("HX-Request"):
        template = "core/components/_cart_drawer_body.html"

    return render(request, template, {
        "cart": cart,
        "cart_items": cart_items,
        "cart_count": cart.total_items(),
    })


@login_required(login_url="login")
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


@login_required(login_url="login")
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


@login_required(login_url="login")
def clear_cart_view(request):
    cart = get_user_cart(request.user)
    cart.clear()
    messages.success(request, "Cart cleared.")
    return redirect("cart")


@login_required(login_url="login")
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
                    requested_size=item.requested_size,
                    requested_color=item.requested_color,
                    availability_status=("pending" if item.product.imported_from_link and item.product.product_type == "preorder" else "not_required"),
                    unit_price=item.product.selling_price(),
                    product_type=item.product.product_type,
                    line_total=item.line_total(),
                )

            order.recalculate_totals()
            if order.items.filter(product__imported_from_link=True, product__product_type="preorder").exists():
                order.availability_status = "awaiting_deposit"
                order.estimated_arrival_start = timezone.now().date() + timedelta(days=14)
                order.estimated_arrival_end = timezone.now().date() + timedelta(days=60)
                order.save(update_fields=["availability_status", "estimated_arrival_start", "estimated_arrival_end", "updated_at"])
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

            messages.success(request, "Order placed successfully. You can track it here and ask the AI assistant if you need help.")
            return redirect("order_detail", order_id=order.id)

    else:
        form = OrderForm()

    return render(request, "core/checkout.html", {
        "form": form,
        "cart": cart,
        "cart_items": cart_items,
        "cart_count": cart.total_items(),
    })


@login_required(login_url="login")
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
                availability_status=("pending" if product.imported_from_link and product.product_type == "preorder" else "not_required"),
            )

            order.recalculate_totals()
            if product.imported_from_link and product.product_type == "preorder":
                order.availability_status = "awaiting_deposit"
                order.estimated_arrival_start = timezone.now().date() + timedelta(days=14)
                order.estimated_arrival_end = timezone.now().date() + timedelta(days=60)
                order.save(update_fields=["availability_status", "estimated_arrival_start", "estimated_arrival_end", "updated_at"])

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

            messages.success(request, "Order placed successfully. You can track it here and ask the AI assistant if you need help.")
            return redirect("order_detail", order_id=order.id)

    else:
        form = OrderForm()

    return render(request, "core/place_order.html", {
        "form": form,
        "product": product,
    })


@login_required(login_url="login")
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


@login_required(login_url="login")
@require_POST
def cancel_after_availability_view(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    if not order.deposit_confirmed or order.availability_status not in ["checking", "options_sent"]:
        messages.error(request, "This order is not eligible for availability cancellation.")
        return redirect("order_detail", order_id=order.id)
    if order.status in ["purchased", "shipped", "in_transit", "arrived", "ready", "successful"]:
        messages.error(request, "This order has already moved beyond availability verification.")
        return redirect("order_detail", order_id=order.id)
    order.availability_status = "cancelled"
    order.status = "cancelled"
    order.refund_status = "due"
    order.refund_amount = order.deposit_amount
    order.save(update_fields=["availability_status", "status", "refund_status", "refund_amount", "updated_at"])
    messages.success(request, "Order cancelled. A 100% refund of your confirmed deposit is now due.")
    send_mail(
        subject=f"Full deposit refund requested - {order.tracking_code}",
        message=f"Order {order.tracking_code} was cancelled by the customer after availability checking. Refund the full deposit: K{order.refund_amount}.",
        from_email=None, recipient_list=[ADMIN_ORDER_EMAIL], fail_silently=True,
    )
    return redirect("order_detail", order_id=order.id)

@login_required(login_url="login")
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


@login_required(login_url="login")
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


def is_approved_supplier(user):
    """Approved suppliers are granted 'core.can_submit_products' by an admin."""
    if not user.is_authenticated:
        return False
    return user.is_staff or user.has_perm("core.can_submit_products")


def supplier_submit_product(request):
    # Anyone may reach this URL, but only approved suppliers see the form.
    # Everyone else gets the "how to become a supplier" page.
    if not is_approved_supplier(request.user):
        return render(request, "core/supplier_access_required.html")

    if request.method == "POST":
        form = SupplierProductRequestForm(
            request.POST,
            request.FILES,
            user=request.user,
        )

        if form.is_valid():
            supplier_request = form.save(commit=False)
            supplier_request.submitted_by = request.user

            # Imported images were already validated and saved to local media storage.
            imported_paths = form.cleaned_data.get("imported_image_paths") or []
            uploaded_images = request.FILES.getlist("images")
            if imported_paths and not request.FILES.get("image"):
                supplier_request.image.name = imported_paths[0]

            # fallback single image
            if not uploaded_images and request.FILES.get("image"):
                supplier_request.image = request.FILES.get("image")

            supplier_request.save()

            # Save locally imported marketplace images.
            for path in imported_paths:
                SupplierProductRequestImage.objects.create(
                    supplier_request=supplier_request,
                    image=path,
                    caption="Imported product image",
                )

            # Save multiple uploaded images
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
        # Prefill the supplier's details from their last submission so
        # repeat posting only needs the product fields.
        last = (
            SupplierProductRequest.objects
            .filter(submitted_by=request.user)
            .order_by("-created_at")
            .first()
        )
        initial = {}
        if last:
            initial = {
                "supplier_name": last.supplier_name,
                "supplier_contact": last.supplier_contact,
            }
        form = SupplierProductRequestForm(initial=initial, user=request.user)

    my_submissions = (
        SupplierProductRequest.objects
        .filter(submitted_by=request.user)
        .order_by("-created_at")[:8]
    )

    return render(
        request,
        "core/supplier_submit_product.html",
        {
            "form": form,
            "my_submissions": my_submissions,
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
    - easier to share with customers
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
        ("SUPPORT", "AI Help", "Ask before buying"),
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
    # SUPPORT SECTION
    # =========================

    wa_y = p(1240)

    draw.rounded_rectangle(
        (p(55), wa_y, p(810), wa_y + p(170)),
        radius=p(24),
        fill=GREEN
    )

    draw.text(
        (p(78), wa_y + p(22)),
        "Order or Ask AI Assistant",
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
        "chinatozambia.org",
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
        "Fast sourcing • Zambia delivery • AI support",
        font=tiny,
        fill=WHITE
    )

    # =========================
    # OUTPUT
    # =========================

    buffer = BytesIO()

    # JPEG is faster for downloads and sharing.
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


