"""Test settings: no external services (in-memory cache, SQLite)."""

from config.settings import *  # noqa: F403

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
WHITENOISE_AUTOREFRESH = True
