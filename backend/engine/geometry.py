"""Polyline maths on (lat, lon) arrays. Vectorised numpy; no per-point Python loops.

Haversine on a sphere is within ~0.5% of the WGS84 ellipsoid, which is well inside
the precision of routing ETAs and forecast grids.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray

from engine.units import FloatArray

EARTH_RADIUS_MI = 3958.7613
METERS_PER_MILE = 1609.344


def haversine_mi(lat1: FloatArray, lon1: FloatArray, lat2: FloatArray, lon2: FloatArray) -> FloatArray:
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi = p2 - p1
    dlmb = np.radians(lon2) - np.radians(lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return np.asarray(2 * EARTH_RADIUS_MI * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0))), dtype=np.float64)


def cumulative_miles(lats: FloatArray, lons: FloatArray) -> FloatArray:
    seg = haversine_mi(lats[:-1], lons[:-1], lats[1:], lons[1:])
    return np.concatenate(([0.0], np.cumsum(seg)))


def initial_bearing_deg(lat1: FloatArray, lon1: FloatArray, lat2: FloatArray, lon2: FloatArray) -> FloatArray:
    """Compass bearing 0..360 (0 = north) from point 1 toward point 2."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dl = np.radians(lon2 - lon1)
    x = np.sin(dl) * np.cos(p2)
    y = np.cos(p1) * np.sin(p2) - np.sin(p1) * np.cos(p2) * np.cos(dl)
    return np.asarray((np.degrees(np.arctan2(x, y)) + 360.0) % 360.0, dtype=np.float64)


@dataclass(frozen=True)
class Polyline:
    """A route line with cumulative distance; points are ordered origin -> destination."""

    lats: FloatArray
    lons: FloatArray
    cum_mi: FloatArray

    @classmethod
    def from_coords(cls, coords: list[tuple[float, float]] | FloatArray) -> Polyline:
        arr = np.asarray(coords, dtype=np.float64)
        if arr.ndim != 2 or arr.shape[1] != 2 or len(arr) < 2:
            raise ValueError("need at least two (lat, lon) points")
        lats, lons = arr[:, 0].copy(), arr[:, 1].copy()
        return cls(lats, lons, cumulative_miles(lats, lons))

    @property
    def length_mi(self) -> float:
        return float(self.cum_mi[-1])

    def _segment_at(self, miles: FloatArray) -> tuple[NDArray[np.intp], FloatArray]:
        """Index of the segment containing each distance, and the fraction along it."""
        d = np.clip(miles, 0.0, self.length_mi)
        idx = np.clip(np.searchsorted(self.cum_mi, d, side="right") - 1, 0, len(self.cum_mi) - 2)
        seg_len = self.cum_mi[idx + 1] - self.cum_mi[idx]
        frac = np.divide(d - self.cum_mi[idx], seg_len, out=np.zeros_like(d), where=seg_len > 0)
        return idx, frac

    def points_at(self, miles: FloatArray) -> tuple[FloatArray, FloatArray]:
        """(lats, lons) at each distance along the line, linear within a segment."""
        idx, frac = self._segment_at(np.asarray(miles, dtype=np.float64))
        lat = self.lats[idx] + frac * (self.lats[idx + 1] - self.lats[idx])
        lon = self.lons[idx] + frac * (self.lons[idx + 1] - self.lons[idx])
        return lat, lon

    def bearings_at(self, miles: FloatArray) -> FloatArray:
        """Road heading at each distance (bearing of the containing segment)."""
        idx, _ = self._segment_at(np.asarray(miles, dtype=np.float64))
        return initial_bearing_deg(self.lats[idx], self.lons[idx], self.lats[idx + 1], self.lons[idx + 1])


def crosswind_mph(wind_mph: FloatArray, wind_from_deg: FloatArray, road_bearing_deg: FloatArray) -> FloatArray:
    """Wind component perpendicular to the road. Direction of travel doesn't matter."""
    return np.abs(np.asarray(wind_mph) * np.sin(np.radians(np.asarray(wind_from_deg) - road_bearing_deg)))
