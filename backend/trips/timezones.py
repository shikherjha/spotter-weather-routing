from functools import lru_cache

from timezonefinder import TimezoneFinder


@lru_cache(maxsize=1)
def _finder() -> TimezoneFinder:
    return TimezoneFinder(in_memory=True)


def tz_at(lat: float, lon: float) -> str:
    """IANA time zone at a point (offline lookup); UTC over open water."""
    return _finder().timezone_at(lng=lon, lat=lat) or "UTC"
