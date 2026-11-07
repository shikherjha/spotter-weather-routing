"""Open-Meteo hourly forecasts for H3 cells, batched and cached.

Design notes:
  * Every request asks for the same absolute window [model run, run + 168 h], so all
    cached cells share one time axis and can be stacked without resampling.
  * Cache key = (model, model-run init time, cell): entries go stale exactly when a
    newer forecast exists, not on an arbitrary TTL.
  * Locations go in POST batches of CHUNK (GET hits URL-length limits), fetched concurrently. Each
    location counts against the free tier's quota, so caching matters.
  * Cells the primary model doesn't cover (NBM is CONUS-only) are refetched from GFS.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import h3
import httpx
import numpy as np
from django.core.cache import cache

from config.env import get_env
from engine.units import HOUR
from engine.weather import WeatherGrid
from providers.http import UpstreamError, fetch, json_or_error

log = logging.getLogger(__name__)

HOURLY = (
    "wind_speed_10m",
    "wind_gusts_10m",
    "wind_direction_10m",
    "rain",
    "showers",
    "snowfall",
    "temperature_2m",
    "weather_code",
)
# Stored layout per cell: (7, H) float32 rows in this order.
ROWS = ("wind", "gust", "dir", "rain", "snow", "temp", "code")
HORIZON_H = 168
CHUNK = 500
FALLBACK_MODEL = "gfs_seamless"
CACHE_TTL_S = 3 * 3600
META_TTL_S = 300
COVERAGE_CHECK_H = 72  # a cell with no data in the first 3 days is outside the model's area


def _iso_hour(ts: int) -> str:
    return datetime.fromtimestamp(ts, UTC).strftime("%Y-%m-%dT%H:%M")


def _col(hourly: dict[str, list[float | None]], name: str) -> np.ndarray:
    return np.array([np.nan if v is None else v for v in hourly[name]], dtype=np.float32)


def _parse_location(loc: dict[str, Any]) -> np.ndarray:
    h = loc["hourly"]
    rain = _col(h, "rain")
    showers = _col(h, "showers")
    rain_total = np.where(np.isnan(rain), showers, rain + np.nan_to_num(showers))
    return np.stack(
        [
            _col(h, "wind_speed_10m"),
            _col(h, "wind_gusts_10m"),
            _col(h, "wind_direction_10m"),
            rain_total,
            _col(h, "snowfall"),
            _col(h, "temperature_2m"),
            _col(h, "weather_code"),
        ]
    )


class OpenMeteoWeather:
    name = "open-meteo"

    def __init__(self, model: str, api_key: str | None = None) -> None:
        self.model = model
        self._key = api_key
        host = "customer-api.open-meteo.com" if api_key else "api.open-meteo.com"
        self._url = f"https://{host}/v1/forecast"
        self._meta_url = f"https://api.open-meteo.com/data/{model}/static/meta.json"

    async def run_init_s(self) -> int:
        """Initialisation time of the latest available model run (unix s)."""
        key = f"wx:meta:{self.model}"
        if (cached := await cache.aget(key)) is not None:
            return int(cached)
        try:
            meta = json_or_error(self.name, await fetch(self.name, "GET", self._meta_url, attempts=1))
            run = int(meta["last_run_initialisation_time"])
        except (UpstreamError, KeyError, TypeError, ValueError) as exc:  # only an optimisation: use the current hour
            log.warning("open-meteo meta unavailable (%s); using current hour", type(exc).__name__)
            run = int(datetime.now(UTC).timestamp() // HOUR * HOUR)
        await cache.aset(key, run, timeout=META_TTL_S)
        return run

    async def grid(self, cells: Sequence[str]) -> WeatherGrid:
        run = await self.run_init_s()
        times = run + HOUR * np.arange(HORIZON_H + 1, dtype=np.float64)
        keys = {c: f"wx:v1:{self.model}:{run}:{c}" for c in cells}
        cached: dict[str, np.ndarray] = await cache.aget_many(list(keys.values()))
        by_cell = {c: cached[k] for c, k in keys.items() if k in cached}

        missing = [c for c in cells if c not in by_cell]
        if missing:
            fetched = await self._fetch(missing, run, self.model)
            uncovered = [c for c, a in fetched.items() if np.isnan(a[0, :COVERAGE_CHECK_H]).all()]
            if uncovered and self.model != FALLBACK_MODEL:
                fetched.update(await self._fetch(uncovered, run, FALLBACK_MODEL))
            by_cell.update(fetched)
            await cache.aset_many({keys[c]: fetched[c] for c in fetched}, timeout=CACHE_TTL_S)

        stack = np.stack([by_cell[c] for c in cells]).astype(np.float64)  # (N, 7, H)
        rows = {name: stack[:, i, :] for i, name in enumerate(ROWS)}
        return WeatherGrid(
            times=times,
            wind_mph=rows["wind"],
            gust_mph=rows["gust"],
            wind_dir_deg=rows["dir"],
            rain_in_hr=rows["rain"],
            snow_in_hr=rows["snow"],
            issued_s=float(run),
            temp_c=rows["temp"],
            weather_code=rows["code"],
        )

    async def _fetch(self, cells: Sequence[str], run: int, model: str) -> dict[str, np.ndarray]:
        """Batches of CHUNK locations, fetched concurrently."""
        chunks = [cells[i : i + CHUNK] for i in range(0, len(cells), CHUNK)]
        parts = await asyncio.gather(*(self._fetch_chunk(c, run, model) for c in chunks))
        return {cell: arr for part in parts for cell, arr in part.items()}

    async def _fetch_chunk(self, chunk: Sequence[str], run: int, model: str) -> dict[str, np.ndarray]:
        centers = [h3.cell_to_latlng(c) for c in chunk]
        data: dict[str, str] = {
            "latitude": ",".join(f"{lat:.4f}" for lat, _ in centers),
            "longitude": ",".join(f"{lon:.4f}" for _, lon in centers),
            "hourly": ",".join(HOURLY),
            "models": model,
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "timeformat": "unixtime",
            "timezone": "GMT",
            "start_hour": _iso_hour(run),
            "end_hour": _iso_hour(int(run + HORIZON_H * HOUR)),
        }
        if self._key:
            data["apikey"] = self._key
        resp = await fetch(self.name, "POST", self._url, data=data)
        if not resp.is_success:
            raise UpstreamError(self.name, _reason(resp) or f"HTTP {resp.status_code}", resp.status_code)
        body = json_or_error(self.name, resp)
        locations = body if isinstance(body, list) else [body]
        if len(locations) != len(chunk):
            raise UpstreamError(self.name, f"expected {len(chunk)} locations, got {len(locations)}")
        out: dict[str, np.ndarray] = {}
        for cell, loc in zip(chunk, locations, strict=True):
            first = (loc.get("hourly") or {}).get("time", [None])[0]
            if first != run:  # every cached cell must share one time axis
                raise UpstreamError(self.name, f"forecast starts at {first}, expected {run}")
            arr = _parse_location(loc)
            if arr.shape[1] != HORIZON_H + 1:
                raise UpstreamError(self.name, f"unexpected hour count {arr.shape[1]}")
            out[cell] = arr
        return out


def _reason(resp: httpx.Response) -> str:
    try:
        return str(resp.json().get("reason", ""))
    except ValueError:
        return ""


def get_weather_provider() -> OpenMeteoWeather:
    env = get_env()
    key = env.open_meteo_api_key.get_secret_value() if env.open_meteo_api_key else None
    return OpenMeteoWeather(env.weather_model, key or None)
