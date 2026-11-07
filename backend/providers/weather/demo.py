"""A simulated storm for demos: the forecast is calm almost every day, which hides most of the product.

Three weather systems, timed relative to the trip's departure so they always meet the truck:
  * a wind storm on I-70 in western Kansas, drifting east (+6 h .. +22 h)
  * a snow band on I-25 over Raton Pass (+8 h .. +21 h)
  * a rain line on I-35 in Oklahoma, drifting north (-2 h .. +7 h)

Placed for Dallas -> Denver; other trips mostly see calm weather. Trips planned with it are
labelled as simulated everywhere they are shown.
"""

from __future__ import annotations

import time
from collections.abc import Sequence

import h3
import numpy as np

from engine.weather import HOUR, WeatherGrid

HORIZON_H = 170


Num = np.ndarray | float


def _blob(lat: np.ndarray, lon: np.ndarray, clat: Num, clon: Num, rlat: float, rlon: float) -> np.ndarray:
    """Gaussian bump centred on (clat, clon) with radii in degrees."""
    return np.exp(-(((lat - clat) / rlat) ** 2 + ((lon - clon) / rlon) ** 2))


def _window(t: np.ndarray, on: float, off: float, ramp_h: float = 3.0) -> np.ndarray:
    """0 outside [on, off], ramping linearly to 1 over `ramp_h` at each end."""
    up = np.clip((t - on) / ramp_h, 0, 1)
    down = np.clip((off - t) / ramp_h, 0, 1)
    return np.minimum(up, down) * ((t >= on) & (t <= off))


class DemoStormWeather:
    model = "demo-storm"

    def __init__(self, departure_s: float) -> None:
        self.departure_s = departure_s

    async def grid(self, cells: Sequence[str]) -> WeatherGrid:
        run = time.time() // HOUR * HOUR - 2 * HOUR
        times = run + HOUR * np.arange(HORIZON_H, dtype=float)
        ll = np.array([h3.cell_to_latlng(c) for c in cells]).reshape(-1, 2)
        lat, lon = ll[:, :1], ll[:, 1:2]
        th = (times[None, :] - self.departure_s) / HOUR

        wind_core = _blob(lat, lon, 38.9, -101.6 + 0.08 * (th - 6), 0.85, 1.6) * _window(th, 6, 22)
        wind = 9 + 3 * np.sin(th / 5) + 43 * wind_core
        snow = 2.5 * _blob(lat, lon, 37.0, -104.5, 0.5, 0.5) * _window(th, 8, 21)
        rain = 0.34 * _blob(lat, lon, 35.2 + 0.12 * th, -97.4, 0.6, 1.0) * _window(th, -2, 7)
        return WeatherGrid(times, wind, wind * 1.35, np.zeros_like(wind) + 285, rain, snow, issued_s=float(run))
