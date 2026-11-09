"""OSRM (public demo server by default). Car profile only: speeds get capped downstream.

Fine for development and as a keyless fallback; the demo server allows ~1 req/s.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

import numpy as np

from providers.http import UpstreamError, fetch, json_or_error
from providers.routing.base import LatLon, RouteCandidate, Truck


class OsrmRouting:
    name = "osrm"
    truck_aware = False

    def __init__(self, base_url: str = "https://router.project-osrm.org") -> None:
        self._base = base_url.rstrip("/")

    async def routes(
        self, waypoints: Sequence[LatLon], depart_at: datetime, truck: Truck, alternatives: int
    ) -> list[RouteCandidate]:
        coords = ";".join(f"{w.lon:.6f},{w.lat:.6f}" for w in waypoints)
        params = {
            "alternatives": str(alternatives) if alternatives and len(waypoints) == 2 else "false",
            "overview": "full",
            "geometries": "geojson",
            "annotations": "duration",
        }
        resp = await fetch(self.name, "GET", f"{self._base}/route/v1/driving/{coords}", params=params)
        body = json_or_error(self.name, resp)
        if body.get("code") != "Ok":
            raise UpstreamError(self.name, body.get("message", body.get("code", "no route")))
        return [self._parse(r) for r in body["routes"]]

    def _parse(self, route: dict[str, Any]) -> RouteCandidate:
        coords = np.asarray([[lat, lon] for lon, lat in route["geometry"]["coordinates"]], dtype=np.float64)
        seg = np.concatenate([leg["annotation"]["duration"] for leg in route["legs"]])
        cum = np.concatenate(([0.0], np.cumsum(seg)))
        if len(cum) != len(coords):  # annotation and geometry disagree: spread the total time evenly
            frac = np.linspace(0.0, 1.0, len(coords))
            cum = frac * float(route["duration"])
        return RouteCandidate(coords, cum, self.name, self.truck_aware)
