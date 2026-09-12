import io
import re

from PIL import Image, UnidentifiedImageError

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand

from core.models import Product, ProductImage

MAX_DIMENSION = 1600
JPEG_QUALITY = 82


def optimize_field(instance, field_name, label, skipped):
    """Re-compress one ImageField in place as an optimized JPEG.

    Returns (before_size, after_size) if converted, or None if skipped/unchanged.
    """
    field = getattr(instance, field_name)
    name = field.name
    if not name:
        return None

    try:
        field.open("rb")
        data = field.read()
    except (IOError, OSError, ValueError):
        skipped.append((label, name, "could not read file"))
        return None
    finally:
        try:
            field.close()
        except Exception:
            pass

    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, OSError):
        skipped.append((label, name, "not a valid image (corrupted?)"))
        return None

    before_size = len(data)

    if image.mode == "RGBA":
        background = Image.new("RGB", image.size, (255, 255, 255))
        background.paste(image, mask=image.split()[-1])
        image = background
    elif image.mode != "RGB":
        image = image.convert("RGB")

    if max(image.size) > MAX_DIMENSION:
        image.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.Resampling.LANCZOS)

    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
    after_bytes = buffer.getvalue()
    after_size = len(after_bytes)

    if after_size >= before_size:
        skipped.append((label, name, "already optimal"))
        return None

    return before_size, after_size, after_bytes, name, field


def apply_conversion(instance, field_name, after_bytes, old_name, field):
    new_name = re.sub(r"\.(png|jpg|jpeg|webp)$", ".jpg", old_name, flags=re.IGNORECASE)
    storage = field.storage
    saved_name = storage.save(new_name, ContentFile(after_bytes))
    setattr(getattr(instance, field_name), "name", saved_name)
    instance.save(update_fields=[field_name])
    if saved_name != old_name:
        storage.delete(old_name)


class Command(BaseCommand):
    help = (
        "Re-compress public product photos (Product.image and ProductImage.customer_image) "
        "as optimized JPEGs so pages load faster. Skips files that are already small or unreadable."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report the savings without changing any files.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        total_before = 0
        total_after = 0
        converted = 0
        skipped = []

        jobs = [
            (photo, "customer_image", f"ProductImage #{photo.pk}")
            for photo in ProductImage.objects.exclude(customer_image="")
        ] + [
            (product, "image", f"Product #{product.pk} ({product.name})")
            for product in Product.objects.exclude(image="")
        ]

        for instance, field_name, label in jobs:
            result = optimize_field(instance, field_name, label, skipped)
            if result is None:
                continue

            before_size, after_size, after_bytes, old_name, field = result
            total_before += before_size
            total_after += after_size
            converted += 1

            if dry_run:
                continue

            apply_conversion(instance, field_name, after_bytes, old_name, field)

        if total_before:
            saved_pct = (1 - total_after / total_before) * 100
            prefix = "[dry run] " if dry_run else ""
            self.stdout.write(self.style.SUCCESS(
                f"{prefix}Converted {converted} image(s): "
                f"{total_before / 1e6:.1f}MB -> {total_after / 1e6:.1f}MB "
                f"({saved_pct:.0f}% smaller)"
            ))
        else:
            self.stdout.write("No images needed optimizing.")

        if skipped:
            self.stdout.write(self.style.WARNING(f"Skipped {len(skipped)} file(s):"))
            for label, name, reason in skipped:
                self.stdout.write(f"  {label} ({name}): {reason}")
