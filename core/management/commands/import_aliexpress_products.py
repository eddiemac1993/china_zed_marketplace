import json
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

import requests
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError

from core.models import Category, Product, money


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def detect_platform(url):
    host = urlparse(url).netloc.lower()
    if "alibaba." in host:
        return "alibaba", "Alibaba"
    if "aliexpress." in host:
        return "aliexpress", "AliExpress"
    return "other", "China supplier"


def clean_text(value):
    return re.sub(r"\s+", " ", value or "").strip()


def first_match(patterns, text):
    for pattern in patterns:
        match = re.search(pattern, text, re.I | re.S)
        if match:
            return clean_text(match.group(1))
    return ""


def parse_decimal(value):
    if value is None:
        return None
    cleaned = re.sub(r"[^0-9.]", "", str(value))
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None


def iter_json_ld(html):
    for match in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.I | re.S,
    ):
        raw = match.group(1).strip()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, list):
            yield from payload
        else:
            yield payload


def find_product_json_ld(html):
    for item in iter_json_ld(html):
        item_type = item.get("@type") if isinstance(item, dict) else ""
        if item_type == "Product" or (isinstance(item_type, list) and "Product" in item_type):
            return item
    return {}


def extract_product_data(html, url):
    platform_code, platform_name = detect_platform(url)
    product_json = find_product_json_ld(html)
    offers = product_json.get("offers") if isinstance(product_json, dict) else {}
    if isinstance(offers, list):
        offers = offers[0] if offers else {}

    title = clean_text(product_json.get("name")) if product_json else ""
    if not title:
        title = first_match(
            [
                r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']',
                r'<title[^>]*>(.*?)</title>',
            ],
            html,
        )
    title = re.sub(r"\s*-\s*(AliExpress|Alibaba\.com).*$", "", title, flags=re.I).strip()

    description = clean_text(product_json.get("description")) if product_json else ""
    if not description:
        description = first_match(
            [
                r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)["\']',
                r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']',
            ],
            html,
        )

    image = product_json.get("image") if product_json else ""
    if isinstance(image, list):
        image = image[0] if image else ""
    if not image:
        image = first_match(
            [r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']'],
            html,
        )

    price = parse_decimal(offers.get("price") if isinstance(offers, dict) else None)
    currency = clean_text(offers.get("priceCurrency") if isinstance(offers, dict) else "")

    if price is None:
        price = parse_decimal(first_match([r'"salePrice"\s*:\s*"([^"]+)"', r'"price"\s*:\s*"([^"]+)"'], html))
    if not currency:
        currency = first_match([r'"priceCurrency"\s*:\s*"([^"]+)"', r'"currencyCode"\s*:\s*"([^"]+)"'], html)

    return {
        "platform_code": platform_code,
        "platform_name": platform_name,
        "title": title or f"{platform_name} product {urlparse(url).path.strip('/').split('/')[-1]}",
        "description": description or f"{platform_name} pre-order product. Final availability and landed Zambia price must be confirmed by ChinaZed staff before sourcing.",
        "image_url": image,
        "price": price,
        "currency": (currency or "USD").upper(),
        "source_link": url,
    }


class Command(BaseCommand):
    help = "Import Alibaba or AliExpress product pages as ChinaZed pre-order products."

    def add_arguments(self, parser):
        parser.add_argument("urls", nargs="*", help="Alibaba or AliExpress product URLs to import.")
        parser.add_argument("--file", help="Text file with one product URL per line.")
        parser.add_argument("--category", default="China Finds", help="Category name to use or create.")
        parser.add_argument("--status", choices=["draft", "active"], default="draft")
        parser.add_argument("--usd-to-rmb", default="7.20", help="USD to RMB conversion rate. Default: 7.20.")
        parser.add_argument("--name", help="Manual product name to use when importing one URL.")
        parser.add_argument("--description", help="Manual product description.")
        parser.add_argument("--price-usd", help="Manual product price in USD when the page price cannot be read.")
        parser.add_argument("--price-rmb", help="Manual product cost in RMB. Overrides --price-usd.")
        parser.add_argument("--image-url", help="Manual product image URL.")
        parser.add_argument("--download-images", action="store_true", help="Download the main product image into the product image field.")
        parser.add_argument("--dry-run", action="store_true", help="Preview scraped product data without saving.")

    def handle(self, *args, **options):
        urls = list(options["urls"])
        if options["file"]:
            with open(options["file"], encoding="utf-8") as handle:
                urls.extend(line.strip() for line in handle if line.strip() and not line.startswith("#"))
        if not urls:
            raise CommandError("Provide at least one AliExpress URL or --file.")
        if len(urls) > 1 and any(options[name] for name in ["name", "description", "price_usd", "price_rmb", "image_url"]):
            raise CommandError("Manual product fields can only be used when importing one URL.")

        usd_to_rmb = parse_decimal(options["usd_to_rmb"])
        if not usd_to_rmb:
            raise CommandError("--usd-to-rmb must be a valid number.")

        category = None
        if not options["dry_run"]:
            category, _ = Category.objects.get_or_create(name=options["category"])

        for url in urls:
            self.stdout.write(f"Fetching {url}")
            response = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
            response.raise_for_status()
            data = extract_product_data(response.text, url)

            if options["name"]:
                data["title"] = options["name"]
            if options["description"]:
                data["description"] = options["description"]
            if options["image_url"]:
                data["image_url"] = options["image_url"]

            manual_rmb_price = parse_decimal(options["price_rmb"])
            manual_usd_price = parse_decimal(options["price_usd"])

            if manual_rmb_price is not None:
                price = manual_rmb_price
                currency = "RMB"
            elif manual_usd_price is not None:
                price = manual_usd_price
                currency = "USD"
            else:
                price = data["price"]
                currency = data["currency"]

            if price is None:
                self.stdout.write(
                    self.style.WARNING(
                        f"Skipped {url}: price was not found. Add --price-usd 25.50 or --price-rmb 183.60."
                    )
                )
                continue

            if currency in {"USD", "US"}:
                rmb_price = money(price * usd_to_rmb)
            elif currency in {"CNY", "RMB", "CN¥", "¥", "CNÂ¥", "Â¥"}:
                rmb_price = money(price)
            else:
                self.stdout.write(self.style.WARNING(f"Skipped {url}: unsupported currency {currency}."))
                continue

            self.stdout.write(f"Title: {data['title']}")
            self.stdout.write(f"Price: {currency} {price} -> RMB {rmb_price}")
            if options["dry_run"]:
                continue

            platform_code = data["platform_code"]
            platform_name = data["platform_name"]

            product, created = Product.objects.update_or_create(
                source_link=url,
                defaults={
                    "name": data["title"][:200],
                    "description": data["description"],
                    "rmb_price": rmb_price,
                    "category": category,
                    "product_type": "preorder",
                    "status": options["status"],
                    "is_available": options["status"] == "active",
                    "delivery_min_days": 14,
                    "delivery_max_days": 30,
                    "source_platform": platform_code,
                    "supplier_name": platform_name,
                    "supplier_note": f"Imported from {platform_name}. Confirm availability, variants, shipping, and final landed price before purchase.",
                },
            )

            if options["download_images"] and data["image_url"] and not product.image:
                image_response = requests.get(data["image_url"], headers={"User-Agent": USER_AGENT}, timeout=20)
                image_response.raise_for_status()
                product.image.save(f"aliexpress-{product.uuid}.jpg", ContentFile(image_response.content), save=True)

            action = "Created" if created else "Updated"
            self.stdout.write(self.style.SUCCESS(f"{action} product #{product.pk}: {product.name}"))
