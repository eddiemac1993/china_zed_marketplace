from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.utils.deconstruct import deconstructible


@deconstructible
class PrivateProductStorage(FileSystemStorage):
    """Filesystem storage outside public MEDIA_ROOT for supplier originals."""

    def __init__(self):
        super().__init__(
            location=settings.PRIVATE_MEDIA_ROOT,
            base_url="/admin/private-product-media/",
        )
