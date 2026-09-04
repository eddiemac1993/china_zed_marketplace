from pathlib import Path
import os
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

DEBUG = os.getenv("DEBUG", "False").lower() in {"1", "true", "yes", "on"}

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "dev-only-secret-key"
    else:
        raise RuntimeError("SECRET_KEY must be set when DEBUG is False.")

DEFAULT_ALLOWED_HOSTS = (
    "chinatozambia.org,"
    "www.chinatozambia.org,"
    "chinatozambia.pythonanywhere.com,"
    "localhost,"
    "127.0.0.1"
)
ALLOWED_HOSTS = [
    host.strip()
    for host in os.getenv("DJANGO_ALLOWED_HOSTS", DEFAULT_ALLOWED_HOSTS).split(",")
    if host.strip()
]

SITE_URL = os.getenv("SITE_URL", "https://chinatozambia.org").rstrip("/")
CSRF_TRUSTED_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in os.getenv(
        "CSRF_TRUSTED_ORIGINS",
        "https://chinatozambia.org,https://www.chinatozambia.org",
    ).split(",")
    if origin.strip()
]


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sitemaps',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'core',
    "events",
    'django.contrib.humanize',
    "pricelist",
    "communinity",
    "loans",
]

# Optional SMS / WhatsApp gateways for loan reminders. Point these at a callable
# ``fn(phone: str, message: str) -> bool``; unset means reminders are audit-logged only.
LOAN_SMS_SENDER = os.getenv("LOAN_SMS_SENDER", "")
LOAN_WHATSAPP_SENDER = os.getenv("LOAN_WHATSAPP_SENDER", "")

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'core.middleware.MobileAppHeadMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'allauth.account.middleware.AccountMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.site_chrome',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}


# Cache
# The default per-process LocMemCache is not shared between web workers, which
# breaks anything that has to agree across requests: Communinity presence counts
# and every rate limit built on cache.get/cache.set. A database cache is shared
# by all workers on any host, including PythonAnywhere.
# Requires: python manage.py createcachetable

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "django_cache",
        "TIMEOUT": 300,
        "OPTIONS": {
            # presence and rate-limit keys are short-lived and churn quickly
            "MAX_ENTRIES": 5000,
            "CULL_FREQUENCY": 3,
        },
    }
}


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = "Africa/Lusaka"

USE_I18N = True

USE_TZ = True

# EMAIL SETTINGS

EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True

EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD")

if DEBUG and not (EMAIL_HOST_USER and EMAIL_HOST_PASSWORD):
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
else:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"

DEFAULT_FROM_EMAIL = EMAIL_HOST_USER or "no-reply@chinatozambia.org"
SITE_OWNER_EMAIL = os.getenv("SITE_OWNER_EMAIL", "chinatozambia.zm@gmail.com").strip()
# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

import os

MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(BASE_DIR, "media")
PRIVATE_MEDIA_ROOT = os.path.join(BASE_DIR, "private_media")

LOGIN_REDIRECT_URL = "profile"
LOGOUT_REDIRECT_URL = "home"
LOGIN_URL = "login"
COMMUNINITY_AI_ENABLED = os.getenv("COMMUNINITY_AI_ENABLED", "True").lower() in {"1", "true", "yes", "on"}

AUTHENTICATION_BACKENDS = [
    "core.backends.EmailOrUsernameBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
]

# Google OAuth credentials belong in the environment, never in source control.
GOOGLE_OAUTH_CLIENT_ID = os.getenv("GOOGLE_OAUTH_CLIENT_ID", "").strip()
GOOGLE_OAUTH_CLIENT_SECRET = os.getenv("GOOGLE_OAUTH_CLIENT_SECRET", "").strip()
GOOGLE_OAUTH_ENABLED = bool(GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET)

SOCIALACCOUNT_LOGIN_ON_GET = False
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_EMAIL_REQUIRED = True
SOCIALACCOUNT_EMAIL_VERIFICATION = "none"
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "SCOPE": ["profile", "email"],
        "AUTH_PARAMS": {"access_type": "online"},
        "OAUTH_PKCE_ENABLED": True,
        "EMAIL_AUTHENTICATION": True,
        "EMAIL_AUTHENTICATION_AUTO_CONNECT": True,
    }
}
if GOOGLE_OAUTH_ENABLED:
    SOCIALACCOUNT_PROVIDERS["google"]["APPS"] = [{
        "client_id": GOOGLE_OAUTH_CLIENT_ID,
        "secret": GOOGLE_OAUTH_CLIENT_SECRET,
        "key": "",
    }]

# Production transport, cookie, and browser hardening.
# PythonAnywhere terminates TLS at its proxy, so forwarded HTTPS must be trusted.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

if DEBUG:
    # Local development is served over plain HTTP, so runserver must not
    # redirect http://127.0.0.1 to https or set secure-only cookies.
    SECURE_SSL_REDIRECT = False
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SECURE_HSTS_SECONDS = 0


# Background Web Push notifications
if "webpush" not in INSTALLED_APPS:
    INSTALLED_APPS.append("webpush")

WEBPUSH_SETTINGS = {
    "VAPID_PUBLIC_KEY": "BKFYzdDgvFtvVAGCdDfu4knCS9uaSCtjWroW8KYvnwKzTJ2u_DBb_xdrPjXdY2PCoFipUEBJpZo0p7tcR6vnz0U",
    "VAPID_PRIVATE_KEY": str(BASE_DIR / "private_key.pem"),
    "VAPID_ADMIN_EMAIL": "chinatozambia.zm@gmail.com",
}
