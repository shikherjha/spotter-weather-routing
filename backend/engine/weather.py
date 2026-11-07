"""Hourly forecasts for many points on one shared time axis, sampled at arbitrary times.

Open-Meteo time semantics (we follow them exactly):
  * wind_speed is instantaneous at the timestamp -> linear interpolation is valid.
  * rain / snowfall / gusts at stamp T cover (T-1h, T] -> pick the bucket that
    *contains* t (first stamp >= t). Interpolating sums or maxima would smear peaks.
Times outside the forecast are reported as invalid, never silently clamped.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np
from numpy.typing import NDArray

from engine.rules import Conditions
from engine.units import HOUR, FloatArray

IntArray = NDArray[np.intp]
BoolArray = NDArray[np.bool_]


@dataclass(frozen=True)
class WeatherGrid:
    times: FloatArray  # (H,) unix seconds, hourly, ascending
    wind_mph: FloatArray  # (N, H)
    gust_mph: FloatArray  # (N, H)
    wind_dir_deg: FloatArray  # (N, H) direction the wind blows FROM
    rain_in_hr: FloatArray  # (N, H) rain + showers
    snow_in_hr: FloatArray  # (N, H)
    issued_s: float  # model run time, for lead-time confidence
    temp_c: FloatArray | None = None  # (N, H) for freezing-precip hints
    weather_code: FloatArray | None = None  # (N, H) WMO code

    def __post_init__(self) -> None:
        h = self.times.shape[0]
        for name in ("wind_mph", "gust_mph", "wind_dir_deg", "rain_in_hr", "snow_in_hr"):
            arr = getattr(self, name)
            if arr.ndim != 2 or arr.shape[1] != h:
                raise ValueError(f"{name} must be (N, {h})")

    @property
    def n_points(self) -> int:
        return int(self.wind_mph.shape[0])


@dataclass(frozen=True)
class Sample:
    """Vectorised weather at (point, time) pairs. Invalid entries are NaN."""

    wind_mph: FloatArray
    gust_mph: FloatArray
    wind_dir_deg: FloatArray
    rain_in_hr: FloatArray
    snow_in_hr: FloatArray
    valid: BoolArray

    def conditions(self, i: int) -> Conditions | None:
        if not self.valid[i]:
            return None
        return Conditions(
            wind_mph=float(self.wind_mph[i]),
            rain_in_hr=float(self.rain_in_hr[i]),
            snow_in_hr=float(self.snow_in_hr[i]),
            gust_mph=float(self.gust_mph[i]),
        )


def sample(grid: WeatherGrid, point_idx: IntArray, t: FloatArray) -> Sample:
    point_idx = np.asarray(point_idx, dtype=np.intp)
    t = np.asarray(t, dtype=np.float64)
    times = grid.times

    # Valid where an accumulation bucket covers t and wind can be interpolated.
    valid = (t >= times[0]) & (t <= times[-1])

    bucket = np.clip(np.searchsorted(times, t, side="left"), 0, len(times) - 1)
    rain = grid.rain_in_hr[point_idx, bucket]
    snow = grid.snow_in_hr[point_idx, bucket]
    gust = grid.gust_mph[point_idx, bucket]

    # Instantaneous wind: interpolate between the bracketing stamps.
    hi = np.clip(np.searchsorted(times, t, side="right"), 1, len(times) - 1)
    lo = hi - 1
    span = times[hi] - times[lo]
    frac = np.clip(np.divide(t - times[lo], span, out=np.zeros_like(t), where=span > 0), 0.0, 1.0)
    w_lo, w_hi = grid.wind_mph[point_idx, lo], grid.wind_mph[point_idx, hi]
    wind = w_lo + frac * (w_hi - w_lo)
    wdir = np.where(frac < 0.5, grid.wind_dir_deg[point_idx, lo], grid.wind_dir_deg[point_idx, hi])

    # Providers return gaps (null -> NaN) past a model's horizon: treat as no forecast.
    valid &= ~(np.isnan(wind) | np.isnan(rain) | np.isnan(snow))
    gust = np.where(np.isnan(gust), wind, gust)
    nan = np.full_like(t, np.nan)

    def mask(a: FloatArray) -> FloatArray:
        return np.where(valid, a, nan)

    return Sample(mask(wind), mask(gust), mask(wdir), mask(rain), mask(snow), valid)


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


def confidence(lead_s: float) -> Confidence:
    """Forecast skill decays with lead time (convective rain fastest)."""
    lead_h = lead_s / HOUR
    if lead_h <= 24:
        return Confidence.HIGH
    if lead_h <= 72:
        return Confidence.MEDIUM
    return Confidence.LOW
