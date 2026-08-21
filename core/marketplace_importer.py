import html as html_lib
import ipaddress
import json
import re
import socket
import uuid
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from io import BytesIO
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from PIL import Image


MAX_PAGE_BYTES = 3 * 1024 * 1024
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_REDIRECTS = 5
MIN_IMAGE_DIMENSION = 300
MAX_IMAGE_DIMENSION = 12000
REQUEST_TIMEOUT = (5, 15)

MARKETPLACE_HOSTS = {
    "aliexpress": {
        "www.aliexpress.com", "aliexpress.com", "m.aliexpress.com",
        "a.aliexpress.com", "s.click.aliexpress.com", "campaign.aliexpress.com",
        "www.aliexpress.us", "aliexpress.us",
    },
    "taobao": {"e.tb.cn", "m.tb.cn", "item.taobao.com", "detail.tmall.com"},
}

IMAGE_HOST_SUFFIXES = (
    "alicdn.com", "aliexpress-media.com", "ae01.alicdn.com",
    "tbcdn.cn", "taobaocdn.com",
)


class ImportFailure(Exception):
    def __init__(self, code, message, status=422):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


@dataclass
class ImportResult:
    platform: str
    source_url: str
    product_id: str = ""
    title: str = ""
    original_title: str = ""
    description: str = ""
    original_description: str = ""
    store_name: str = ""
    currency: str = ""
    price_min: str = ""
    price_max: str = ""
    original_price: str = ""
    colors: list = field(default_factory=list)
    sizes: list = field(default_factory=list)
    variants: list = field(default_factory=list)
    image_urls: list = field(default_factory=list)
    local_image_paths: list = field(default_factory=list)
    warnings: list = field(default_factory=list)

    @property
    def price_display(self):
        if not self.price_min:
            return ""
        if self.price_max and self.price_max != self.price_min:
            return f"{self.currency} {self.price_min}–{self.price_max}".strip()
        return f"{self.currency} {self.price_min}".strip()

    @property
    def complete(self):
        return bool(
            self.title and self.description and self.local_image_paths
            and self.price_min and (self.colors or self.sizes or self.variants)
        )

    def as_dict(self):
        return {
            "platform": self.platform,
            "source_platform": self.platform,
            "source_url": self.source_url,
            "source_link": self.source_url,
            "product_id": self.product_id,
            "name": self.title,
            "original_name": self.original_title,
            "description": self.description,
            "original_description": self.original_description,
            "store_name": self.store_name,
            "currency": self.currency,
            "price_min": self.price_min,
            "price_max": self.price_max,
            "original_price": self.original_price,
            "price_display": self.price_display,
            "colors": self.colors,
            "sizes": self.sizes,
            "variants": self.variants,
            "images": self.image_urls,
            "local_image_paths": self.local_image_paths,
            "warnings": self.warnings,
            "complete": self.complete,
            "status": "complete" if self.complete else "partial",
            "status_message": (
                "All extractable product information was imported. Confirm the exact variant, "
                "supplier price, quantity and contact details before submission."
                if self.complete else
                "Basic information imported — please confirm the price, variants, quantity and photos."
            ),
            "price_notice": (
                "Displayed AliExpress price — verify the selected variant and shipping cost before submission."
                if self.platform == "aliexpress" else
                "Displayed marketplace price — verify the selected variant and shipping cost before submission."
            ),
            "delivery": "14 to 60 days",
        }


def extract_first_url(value):
    match = re.search(r"https?://[^\s<>\]\[()]+", value or "", flags=re.I)
    if not match:
        raise ImportFailure("invalid_link", "Paste a complete AliExpress or Taobao product link.", 400)
    return html_lib.unescape(match.group(0).rstrip(".,;，。'\""))


def detect_platform(url):
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    for platform, hosts in MARKETPLACE_HOSTS.items():
        if host in hosts:
            return platform
    raise ImportFailure("unsupported_link", "Only approved AliExpress and Taobao links are supported.", 400)


def _validate_public_host(url, allowed_hosts=None, allow_image_host=False):
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ImportFailure("invalid_link", "The marketplace URL is invalid.", 400)
    host = parsed.hostname.lower().rstrip(".")
    if allowed_hosts and host not in allowed_hosts:
        raise ImportFailure("blocked_redirect", "The link redirected to an unsupported website.", 400)
    if allow_image_host and not any(host == suffix or host.endswith("." + suffix) for suffix in IMAGE_HOST_SUFFIXES):
        raise ImportFailure("blocked_image", "An image URL used an unsupported host.", 400)
    try:
        records = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ImportFailure("dns_failure", "The marketplace hostname could not be resolved.") from exc
    for record in records:
        address = ipaddress.ip_address(record[4][0])
        if not address.is_global:
            raise ImportFailure("blocked_address", "Private, loopback, reserved and link-local addresses are blocked.", 400)
    return host


def _read_limited(response, limit):
    chunks = []
    size = 0
    for chunk in response.iter_content(65536):
        if not chunk:
            continue
        size += len(chunk)
        if size > limit:
            raise ImportFailure("response_too_large", "The remote response exceeded the allowed size.")
        chunks.append(chunk)
    return b"".join(chunks)


def safe_get(url, allowed_hosts, *, limit=MAX_PAGE_BYTES, accept_images=False, session=None):
    client = session or requests.Session()
    current = url
    for redirect_count in range(MAX_REDIRECTS + 1):
        _validate_public_host(current, allowed_hosts, allow_image_host=accept_images)
        try:
            response = client.get(
                current,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; ChinaZedProductImporter/2.0)",
                    "Accept-Language": "en-US,en;q=0.9",
                },
                timeout=REQUEST_TIMEOUT,
                allow_redirects=False,
                stream=True,
            )
        except requests.Timeout as exc:
            raise ImportFailure("timeout", "The marketplace request timed out. Please try again.") from exc
        except requests.RequestException as exc:
            raise ImportFailure("request_failed", "The marketplace page could not be retrieved.") from exc
        if response.status_code in {301, 302, 303, 307, 308}:
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise ImportFailure("redirect_failure", "The marketplace returned an invalid redirect.")
            if redirect_count >= MAX_REDIRECTS:
                raise ImportFailure("redirect_failure", "The marketplace used too many redirects.")
            current = urljoin(current, location)
            continue
        if response.status_code in {404, 410}:
            raise ImportFailure("product_removed", "This product has been removed or is no longer available.", 404)
        if response.status_code in {401, 403, 429}:
            raise ImportFailure("login_or_captcha", "AliExpress requires login or CAPTCHA verification for this product.")
        try:
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ImportFailure("request_failed", "The marketplace returned an unexpected error.") from exc
        body = _read_limited(response, limit)
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
        response.close()
        return current, content_type, body
    raise ImportFailure("redirect_failure", "The marketplace redirect could not be resolved.")


def _meta_content(page_html, key):
    for tag in re.findall(r"<meta\b[^>]*>", page_html, flags=re.I):
        attrs = dict(
            (name.lower(), html_lib.unescape(value))
            for name, _, value in re.findall(r"""([\w:-]+)\s*=\s*(["'])(.*?)\2""", tag, flags=re.S)
        )
        if attrs.get("property", "").lower() == key.lower() or attrs.get("name", "").lower() == key.lower():
            return attrs.get("content", "").strip()
    return ""


def _json_scripts(page_html):
    results = []
    pattern = r"<script\b([^>]*)>(.*?)</script>"
    for attrs, content in re.findall(pattern, page_html, flags=re.I | re.S):
        if "json" not in attrs.lower() and not content.lstrip().startswith(("{", "[")):
            continue
        try:
            results.append(json.loads(html_lib.unescape(content.strip())))
        except (json.JSONDecodeError, TypeError):
            continue
    return results


def _walk_json(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _first(mapping_nodes, keys, default=""):
    lowered = {key.lower() for key in keys}
    for node in mapping_nodes:
        for key, value in node.items():
            if key.lower() in lowered and isinstance(value, (str, int, float)) and str(value).strip():
                return str(value).strip()
    return default


def _decimal_string(value):
    try:
        return str(Decimal(str(value).replace(",", "").strip()).quantize(Decimal("0.01")))
    except (InvalidOperation, ValueError, TypeError):
        return ""


def _collect_images(nodes, page_html):
    images = []
    for key in ("og:image", "twitter:image"):
        value = _meta_content(page_html, key)
        if value:
            images.append(value)
    for node in nodes:
        for key, value in node.items():
            if "image" not in key.lower() and "pic" not in key.lower():
                continue
            candidates = value if isinstance(value, list) else [value]
            for candidate in candidates:
                if isinstance(candidate, dict):
                    candidate = candidate.get("url") or candidate.get("imageUrl")
                if isinstance(candidate, str):
                    candidate = html_lib.unescape(candidate.replace("\\/", "/"))
                    if candidate.startswith("//"):
                        candidate = "https:" + candidate
                    if candidate.startswith("http") and candidate not in images:
                        images.append(candidate)
    return images[:16]


def _collect_variants(nodes):
    colors, sizes, variants, prices = [], [], [], []
    for node in nodes:
        label = str(node.get("skuPropertyName") or node.get("name") or node.get("propertyName") or "").lower()
        values = node.get("skuPropertyValues") or node.get("values") or node.get("propertyValues")
        if isinstance(values, list):
            clean_values = []
            for value in values:
                if isinstance(value, dict):
                    clean = value.get("propertyValueDisplayName") or value.get("name") or value.get("value")
                else:
                    clean = value
                if clean and str(clean) not in clean_values:
                    clean_values.append(str(clean))
            if clean_values:
                variants.append({"name": label or "option", "values": clean_values})
                if "color" in label or "colour" in label:
                    colors.extend(v for v in clean_values if v not in colors)
                if "size" in label:
                    sizes.extend(v for v in clean_values if v not in sizes)
        for key in ("salePrice", "price", "activityPrice", "skuVal"):
            value = node.get(key)
            if isinstance(value, (str, int, float)):
                clean = _decimal_string(value)
                if clean:
                    prices.append(Decimal(clean))
            elif isinstance(value, dict):
                for subkey in ("value", "minPrice", "maxPrice"):
                    clean = _decimal_string(value.get(subkey))
                    if clean:
                        prices.append(Decimal(clean))
    return colors, sizes, variants, prices


def parse_marketplace_html(platform, source_url, page_html, share_text=""):
    lower_page = page_html.lower()
    if any(marker in lower_page for marker in ("captcha", "punish page", "login.aliexpress", "x5sec")):
        raise ImportFailure("login_or_captcha", "AliExpress requires login or CAPTCHA verification for this product.")
    if any(marker in lower_page for marker in ("product is no longer available", "item is unavailable", "product removed")):
        raise ImportFailure("product_removed", "This product has been removed or is no longer available.", 404)

    scripts = _json_scripts(page_html)
    nodes = list(_walk_json(scripts))
    result = ImportResult(platform=platform, source_url=source_url)
    parsed = urlparse(source_url)
    id_match = re.search(r"/(?:item/)?(\d{6,})\.html", parsed.path) or re.search(r"[?&]id=(\d{6,})", source_url)
    result.product_id = id_match.group(1) if id_match else _first(nodes, {"productId", "itemId", "product_id"})

    shared_title = re.search(r"「([^」]{3,500})」", share_text or "")
    title = _meta_content(page_html, "og:title") or _first(nodes, {"name", "title", "subject", "productTitle"})
    if not title and shared_title:
        title = shared_title.group(1)
    result.original_title = html_lib.unescape(title or "").strip()
    result.title = result.original_title

    description = _meta_content(page_html, "og:description") or _first(nodes, {"description", "productDescription", "seoDescription"})
    result.original_description = html_lib.unescape(re.sub(r"<[^>]+>", " ", description or result.original_title)).strip()
    result.description = re.sub(r"\s+", " ", result.original_description)
    result.store_name = _first(nodes, {"storeName", "sellerName", "shopName", "companyName"})
    result.currency = _first(nodes, {"priceCurrency", "currency", "currencyCode"}, "CNY" if platform == "taobao" else "")

    colors, sizes, variants, prices = _collect_variants(nodes)
    result.colors, result.sizes, result.variants = colors, sizes, variants
    result.image_urls = _collect_images(nodes, page_html)

    jsonld_prices = []
    for node in nodes:
        offers = node.get("offers")
        if isinstance(offers, dict):
            for key in ("price", "lowPrice", "highPrice"):
                clean = _decimal_string(offers.get(key))
                if clean:
                    jsonld_prices.append(Decimal(clean))
            result.currency = str(offers.get("priceCurrency") or result.currency)
    prices.extend(jsonld_prices)
    if prices:
        result.price_min = str(min(prices).quantize(Decimal("0.01")))
        result.price_max = str(max(prices).quantize(Decimal("0.01")))
    original = _first(nodes, {"originalPrice", "listPrice", "oldPrice"})
    result.original_price = _decimal_string(original)
    if not result.price_min:
        meta_price = _meta_content(page_html, "product:price:amount")
        result.price_min = result.price_max = _decimal_string(meta_price)
    if not result.currency:
        result.currency = _meta_content(page_html, "product:price:currency")

    if not result.title:
        raise ImportFailure("product_data_unavailable", "The page opened, but the marketplace did not expose product information.")
    if not result.price_min:
        result.warnings.append("Price unavailable — confirm the supplier price manually.")
    if not result.image_urls:
        result.warnings.append("Images unavailable — upload at least one product photo manually.")
    return result


def download_product_images(result, owner_id, max_images=12):
    saved = []
    for index, image_url in enumerate(result.image_urls[:max_images]):
        try:
            final_url, content_type, body = safe_get(
                image_url,
                allowed_hosts=None,
                limit=MAX_IMAGE_BYTES,
                accept_images=True,
            )
            if content_type not in {"image/jpeg", "image/png", "image/webp", "image/avif"}:
                continue
            image = Image.open(BytesIO(body))
            image.verify()
            image = Image.open(BytesIO(body))
            width, height = image.size
            if min(width, height) < MIN_IMAGE_DIMENSION or max(width, height) > MAX_IMAGE_DIMENSION:
                continue
            suffix = Path(urlparse(final_url).path).suffix.lower()
            if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".avif"}:
                suffix = ".jpg"
            name = f"supplier_imports/{owner_id}/{uuid.uuid4().hex}-{index}{suffix}"
            saved.append(default_storage.save(name, ContentFile(body)))
        except (ImportFailure, OSError, ValueError):
            continue
    result.local_image_paths = saved
    if result.image_urls and not saved:
        result.warnings.append("Images were found but failed safety or quality validation.")
    return result


def import_marketplace_product(share_text, owner_id, translate=None, session=None, download_images=True):
    source_url = extract_first_url(share_text)
    platform = detect_platform(source_url)
    final_url, content_type, body = safe_get(
        source_url,
        MARKETPLACE_HOSTS[platform],
        session=session,
    )
    if "html" not in content_type and content_type not in {"", "text/plain"}:
        raise ImportFailure("unsupported_response", "The marketplace did not return a product page.")
    page_html = body.decode("utf-8", errors="replace")
    result = parse_marketplace_html(platform, final_url, page_html, share_text)
    if translate:
        result.title = translate(result.original_title)
        result.description = translate(result.original_description)
    if download_images:
        download_product_images(result, owner_id)
    return result

