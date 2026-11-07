from pathlib import Path

import dj_database_url

from config.env import get_env

env = get_env()
BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = env.django_secret_key.get_secret_value()
DEBUG = env.django_debug
ALLOWED_HOSTS = env.allowed_hosts

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.staticfiles",
    "corsheaders",
    "api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.gzip.GZipMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
ASGI_APPLICATION = "config.asgi.application"
WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {"default": dj_database_url.parse(env.database_url, conn_max_age=60)}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CACHES = (
    {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": env.redis_url}}
    if env.redis_url
    else {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
)

CORS_ALLOWED_ORIGINS = env.cors_origins

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

USE_TZ = True
TIME_ZONE = "UTC"

TEMPLATES: list[dict[str, object]] = []

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
