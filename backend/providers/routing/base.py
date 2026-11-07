from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import numpy as np

from engine.geometry import FloatArray, cumulative_miles


@dataclass(frozen=True)
class LatLon:
    lat: float
    lon: float

    def __str__(self) -> str:
        return f"{self.lat:.6f},{self.lon:.6f}"


@dataclass(frozen=True)
class RouteCandidate:
    coords: FloatArray  # (N, 2) lat, lon
    cum_drive_s: FloatArray  # (N,) moving seconds at each vertex
    provider: str
    truck_aware: bool  # False -> speeds are car speeds and must be capped

    @property
    def duration_s(self) -> float:
        return float(self.cum_drive_s[-1])


class RoutingProvider(Protocol):
    name: str
    truck_aware: bool

    async def routes(
        self, waypoints: Sequence[LatLon], depart_at: datetime, load_lb: float, alternatives: int
    ) -> list[RouteCandidate]: ...


def times_from_anchors(coords: FloatArray, anchor_idx: Sequence[int], anchor_s: Sequence[float]) -> FloatArray:
    """Spread sparse (vertex index -> seconds) anchors over every vertex, proportional to distance."""
    cum = cumulative_miles(coords[:, 0], coords[:, 1])
    idx = np.asarray(anchor_idx, dtype=np.intp)
    secs = np.maximum.accumulate(np.asarray(anchor_s, dtype=np.float64))
    if idx[0] != 0:
        idx, secs = np.concatenate(([0], idx)), np.concatenate(([0.0], secs))
    return np.asarray(np.interp(cum, cum[idx], secs), dtype=np.float64)
