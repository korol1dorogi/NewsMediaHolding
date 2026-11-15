from pathlib import Path

from .env import env_bool, env_int, env_list, env_str

BASE_DIR = Path(__file__).resolve().parent.parent

DEBUG = env_bool("DJANGO_DEBUG", False)
SECRET_KEY = env_str("DJANGO_SECRET_KEY", "local-dev-placeholder-change-me")
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", ["localhost", "127.0.0.1", "web", "backend"])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "apps.core",
    "apps.accounts",
    "apps.cases",
    "apps.payments",
    "apps.companies",
    "apps.claims",
]

AUTH_USER_MODEL = "accounts.User"
CSRF_FAILURE_VIEW = "apps.accounts.errors.csrf_failure"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env_str("POSTGRES_DB", "app"),
        "USER": env_str("POSTGRES_USER", "app"),
        "PASSWORD": env_str("POSTGRES_PASSWORD", "app-local-placeholder"),
        "HOST": env_str("POSTGRES_HOST", "db"),
        "PORT": env_int("POSTGRES_PORT", 5432),
        "CONN_MAX_AGE": 60,
        "OPTIONS": {"connect_timeout": 3},
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

LANGUAGE_CODE = "ru-ru"
TIME_ZONE = "Europe/Moscow"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# One origin: frontend and API are served by Caddy on the same host.
# Sessions + CSRF, no CORS.
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
# Enable only when the application is reached over HTTPS. Local HTTP stays usable.
# The process environment must explicitly carry this setting in each deployment.
HTTPS_SECURE_COOKIES = env_bool("HTTPS_SECURE_COOKIES", False)
SESSION_COOKIE_SECURE = HTTPS_SECURE_COOKIES
CSRF_COOKIE_SECURE = HTTPS_SECURE_COOKIES
CSRF_TRUSTED_ORIGINS = env_list(
    "CSRF_TRUSTED_ORIGINS", ["http://localhost:8080", "http://127.0.0.1:8080"]
)
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.accounts.authentication.SessionAuthentication401",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "EXCEPTION_HANDLER": "apps.accounts.errors.exception_handler",
}

REDIS_URL = env_str("REDIS_URL", "redis://redis:6379/0")
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "KEY_PREFIX": "nmh-auth",
    }
}
AUTH_LOGIN_ATTEMPTS = max(1, env_int("AUTH_LOGIN_ATTEMPTS", 10))
AUTH_LOGIN_WINDOW_SECONDS = max(1, env_int("AUTH_LOGIN_WINDOW_SECONDS", 60))
AUTH_TRUST_PROXY_HEADER = env_bool("AUTH_TRUST_PROXY_HEADER", False)
DEMO_USER_PASSWORD = env_str("DEMO_USER_PASSWORD", "demo-user-placeholder")
DEMO_LAWYER_PASSWORD = env_str("DEMO_LAWYER_PASSWORD", "demo-lawyer-placeholder")
DEMO_MODERATOR_PASSWORD = env_str("DEMO_MODERATOR_PASSWORD", "demo-moderator-placeholder")
DEMO_EDITOR_PASSWORD = env_str("DEMO_EDITOR_PASSWORD", "demo-editor-placeholder")
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TASK_ALWAYS_EAGER = env_bool("CELERY_TASK_ALWAYS_EAGER", False)

LLM_PROVIDER = env_str("LLM_PROVIDER", "mock")
LLM_BASE_URL = env_str("LLM_BASE_URL", "")
LLM_API_KEY = env_str("LLM_API_KEY", "")
LLM_MODEL = env_str("LLM_MODEL", "")
# Mock fixture name: backend/apps/llm/mock_responses/<task>/<scenario>.json
LLM_MOCK_SCENARIO = env_str("LLM_MOCK_SCENARIO", "demo")

# Company check by INN: "mock" (demo cache, no network) or "dadata".
COMPANIES_PROVIDER = env_str("COMPANIES_PROVIDER", "mock")
COMPANIES_API_KEY = env_str("COMPANIES_API_KEY", "")
COMPANIES_API_URL = env_str(
    "COMPANIES_API_URL",
    "https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party",
)

# Timeouts from docs/product.md (placeholders, open to discussion).
CLAIM_REVIEW_TIMEOUT_HOURS = max(1, env_int("CLAIM_REVIEW_TIMEOUT_HOURS", 4))
OFFERS_WINDOW_HOURS = max(1, env_int("OFFERS_WINDOW_HOURS", 48))
WORK_ACCEPTANCE_DAYS = max(1, env_int("WORK_ACCEPTANCE_DAYS", 3))

# Documents: private DB blobs, served only through the owner-checked endpoint.
DOCUMENTS_MAX_BYTES = max(1, env_int("DOCUMENTS_MAX_BYTES", 5 * 1024 * 1024))
DOCUMENTS_MAX_PER_CASE = max(1, env_int("DOCUMENTS_MAX_PER_CASE", 10))

# Payments: demo escrow, no real money. Amounts in kopecks, shares in basis points (1% = 100).
# Placeholders from docs/product.md, open to the financial model.
PAYMENTS_PROVIDER = env_str("PAYMENTS_PROVIDER", "demo")
PAYMENTS_CLAIM_PRICE_KOPECKS = env_int("PAYMENTS_CLAIM_PRICE_KOPECKS", 149_000)
PAYMENTS_REVIEWER_SHARE_BP = env_int("PAYMENTS_REVIEWER_SHARE_BP", 7_000)
PAYMENTS_PLATFORM_FEE_BP = env_int("PAYMENTS_PLATFORM_FEE_BP", 1_000)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": env_str("DJANGO_LOG_LEVEL", "INFO")},
}
