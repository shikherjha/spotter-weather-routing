"""A simulated storm, and the warnings the NWS would issue for it, for demos and walkthroughs.

Live forecasts are calm most days, which leaves the ranking, load rules and departure advice
nothing to do.

Three weather systems, timed from the next whole hour (when the demo trip leaves), so a trip
re-planned for a later departure sees the same storm and can actually avoid it:
  * a wind storm on I-70 in western Kansas, drifting east (+6 h .. +22 h)
  * a snow band on I-25 over Raton Pass (+8 h .. +21 h)
  * a rain line on I-35 in Oklahoma, drifting north (-2 h .. +7 h)

Placed for Dallas -> Denver; other trips mostly see calm weather. Trips planned with it are
labelled as simulated everywhere they are shown.
"""

from __future__ import annotations

import math
import time
from collections.abc import Sequence

import h3
import numpy as np
from shapely.geometry import Polygon

from engine.units import HOUR
from engine.weather import WeatherGrid
from providers.nws import Alert

HORIZON_H = 168  # same window as Open-Meteo
GUST_FACTOR = 1.35  # gusts run about a third above sustained wind in a strong westerly
WIND_FROM_DEG = 285.0


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
    model = "demo_storm"  # same string as the request's weather="demo_storm"

    def __init__(self, now_s: float | None = None) -> None:
        now = time.time() if now_s is None else now_s
        self.anchor_s = (now // HOUR + 1) * HOUR

    async def grid(self, cells: Sequence[str]) -> WeatherGrid:
        run = self.anchor_s - 3 * HOUR
        times = run + HOUR * np.arange(HORIZON_H, dtype=float)
        ll = np.array([h3.cell_to_latlng(c) for c in cells]).reshape(-1, 2)
        lat, lon = ll[:, :1], ll[:, 1:2]
        th = (times[None, :] - self.anchor_s) / HOUR

        wind_core = _blob(lat, lon, 38.9, -101.6 + 0.08 * (th - 6), 0.85, 1.6) * _window(th, 6, 22)
        wind = 9 + 3 * np.sin(th / 5) + 43 * wind_core
        snow = 2.5 * _blob(lat, lon, 37.0, -104.5, 0.5, 0.5) * _window(th, 8, 21)
        rain = 0.34 * _blob(lat, lon, 35.2 + 0.12 * th, -97.4, 0.6, 1.0) * _window(th, -2, 7)
        gust = wind * GUST_FACTOR
        westerly = np.full_like(wind, WIND_FROM_DEG)
        return WeatherGrid(times, wind, gust, westerly, rain, snow, issued_s=float(run))


def _ellipse(lat: float, lon: float, rlat: float, rlon: float) -> Polygon:
    return Polygon(
        [(lon + rlon * math.cos(t), lat + rlat * math.sin(t)) for t in (i * math.pi / 18 for i in range(36))]
    )


def demo_alerts(anchor_s: float) -> list[Alert]:
    h = 3600
    return [
        Alert(
            id=f"demo-winter-storm-{int(anchor_s)}",
            event="Winter Storm Warning",
            severity="Severe",
            headline="Winter Storm Warning (simulated)",
            nws_headline="",
            description=(
                "* WHAT...Heavy snow expected. Total snow accumulations of 6 to 10 inches, with up to\n"
                "14 inches over Raton Pass. Snowfall rates of 2 to 3 inches per hour at times.\n\n"
                "* WHERE...Raton Pass, Trinidad and the I-25 corridor.\n\n"
                "* WHEN...Through tonight.\n\n"
                "* IMPACTS...Travel could be very difficult to impossible. Roads, including\n"
                "Interstate 25 over Raton Pass, may close."
            ),
            instruction="If you must travel, keep an extra flashlight, food and water in your vehicle.",
            area="Raton Pass; Trinidad; Southern Colfax County",
            starts=anchor_s + 7 * h,
            ends=anchor_s + 22 * h,
            ugc=frozenset(),
            polygon=_ellipse(37.05, -104.5, 0.55, 0.5),
        ),
        Alert(
            id=f"demo-high-wind-{int(anchor_s)}",
            event="High Wind Warning",
            severity="Severe",
            headline="High Wind Warning (simulated)",
            nws_headline="",
            description=(
                "* WHAT...West winds 40 to 50 mph with gusts up to 65 mph.\n\n"
                "* WHERE...Northwest Kansas along Interstate 70.\n\n"
                "* WHEN...From this evening through Sunday morning.\n\n"
                "* IMPACTS...Travel will be difficult, especially for high profile vehicles. "
                "Blowing dust may reduce visibility."
            ),
            instruction="Drivers of high profile vehicles should consider delaying travel.",
            area="Sherman; Thomas; Logan; Gove; Trego",
            starts=anchor_s + 5 * h,
            ends=anchor_s + 23 * h,
            ugc=frozenset(),
            polygon=_ellipse(39.0, -101.0, 0.6, 1.8),
        ),
        Alert(
            id=f"demo-frost-{int(anchor_s)}",
            event="Frost Advisory",
            severity="Minor",
            headline="Frost Advisory (simulated)",
            nws_headline="",
            description=(
                "* WHAT...Temperatures as low as 33 will result in frost formation.\n\n"
                "* WHERE...The Texas Panhandle.\n\n"
                "* IMPACTS...Frost could harm sensitive outdoor vegetation."
            ),
            instruction="Take steps now to protect tender plants from the cold.",
            area="Potter; Randall; Oldham; Deaf Smith",
            starts=anchor_s,
            ends=anchor_s + 20 * h,
            ugc=frozenset(),
            polygon=_ellipse(35.2, -101.9, 0.7, 1.0),
        ),
    ]
