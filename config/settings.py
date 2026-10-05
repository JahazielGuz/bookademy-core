from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(DEBUG=(bool, False))
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="dev-only-change-me")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "accounts",
    "documents",
    "curriculum",
    "progress",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
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
            ]
        },
    }
]

DATABASES = {"default": env.db("DATABASE_URL")}

AUTH_USER_MODEL = "accounts.User"

# Argon2id first: the default PBKDF2 is the weaker option and this is a greenfield
# database, so there is nothing to stay compatible with.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

# Length only. The common-password and all-numeric rules were rejecting passwords
# people actually wanted to use on a learning app that stores nothing sensitive, and
# a rule that sends someone to a password manager to read a PDF is not worth its cost.
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=14),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": False,
}

# bookademy-web is the only browser client; it calls this API from its server side.
CORS_ALLOWED_ORIGINS = [env("WEB_ORIGIN", default="http://localhost:3000")]

CELERY_BROKER_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1

# A thread pool, not the default prefork. These tasks do nothing but wait on HTTP
# and write rows, so threads are the right shape for them — and prefork additionally
# crashes on macOS under Python 3.12, where the spawned child cannot resolve the task
# registry ("not enough values to unpack") and the task dies before any of its code
# runs, leaving the document stuck in `pending` with no error to show.
CELERY_WORKER_POOL = "threads"

# Redis redelivers any task still unacknowledged after this long, and with acks_late
# a generation run is unacknowledged for its whole duration. At the default of one
# hour a long book was redelivered every hour and restarted from chapter one, running
# alongside itself. The document lock makes that harmless; this makes it rare.
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": 6 * 3600}
CELERY_WORKER_CONCURRENCY = 4

AI_SERVICE_URL = env("AI_SERVICE_URL", default="http://localhost:8001")
SERVICE_TOKEN = env("SERVICE_TOKEN", default="dev-only-change-me")

# A 300-page book takes the model minutes, not seconds.
AI_SERVICE_TIMEOUT_SECONDS = 600

# US dollars per million tokens. Kept here rather than in code so a price change is a
# config edit, and so a model missing from this table costs a visible $0.00 rather
# than silently guessing.
MODEL_PRICES = {
    "gpt-4o-mini": {"input": 0.15, "cached": 0.075, "output": 0.60},
    "gpt-4o": {"input": 2.50, "cached": 1.25, "output": 10.00},
    "gpt-5-mini": {"input": 0.25, "cached": 0.025, "output": 2.00},
    "gpt-5-nano": {"input": 0.05, "cached": 0.005, "output": 0.40},
    "gpt-5.1": {"input": 1.25, "cached": 0.125, "output": 10.00},
    "gpt-4.1-mini": {"input": 0.40, "cached": 0.10, "output": 1.60},
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
