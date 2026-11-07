"""Test settings: no external services (in-memory cache)."""

from config.settings import *  # noqa: F403

CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
WHITENOISE_AUTOREFRESH = True
