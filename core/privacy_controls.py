import json
import time
from urllib.parse import unquote


def has_optional_consent(request, category):
    try:
        value = json.loads(unquote(request.COOKIES.get('czConsent', '')))
        age = time.time() - value.get('savedAt', 0) / 1000
        return value.get('version') == 2 and 0 <= age < 180 * 86400 and value.get(category) is True
    except (ValueError, TypeError, AttributeError):
        return False
