"""Valhalla (open source, self-hosted on OpenStreetMap) in truck mode.

Truck costing keeps the route off roads with lower clearances, weight limits or hazmat bans,
and the server is ours, so a route costs no API call and comes back in well under a second.
Moving time per vertex comes from the maneuver list: each maneuver's time is spread over its
part of the shape.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

import httpx
import numpy as np

from providers.http import UpstreamError, fetch, json_or_error
from providers.routing.base import LatLon, RouteCandidate, Truck, times_from_anchors

LB_TO_TONNE = 0.00045359237
FT_TO_M = 0.3048
# Valhalla's "there is no route" answers (no path, no road near a point, unconnected regions):
# the request is fine, the truck just can't get there. Anything else is the server's problem.
NO_ROUTE_CODES = frozenset({170, 171, 442, 443})
TIMEOUT_S = 10.0  # our own server answers in about a second; past this, use the backup


def decode_polyline6(encoded: str) -> np.ndarray:
    """Google's encoded polyline at 1e-6 precision, as Valhalla returns it -> (N, 2) lat, lon."""
    coords: list[tuple[float, float]] = []
    index = lat = lon = 0
    while index < len(encoded):
        for axis in (0, 1):
            shift = result = 0
            while True:
                byte = ord(encoded[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if axis == 0:
                lat += delta
            else:
                lon += delta
        coords.append((lat / 1e6, lon / 1e6))
    return np.asarray(coords, dtype=np.float64)


class ValhallaRouting:
    name = "valhalla"
    truck_aware = True

    def __init__(self, base_url: str, token: str | None = None) -> None:
        self._url = base_url.rstrip("/") + "/route"
        self._headers = {"Authorization": f"Bearer {token}"} if token else {}

    async def routes(
        self, waypoints: Sequence[LatLon], depart_at: datetime, truck: Truck, alternatives: int
    ) -> list[RouteCandidate]:
        body: dict[str, Any] = {
            "locations": [
                {"lat": w.lat, "lon": w.lon, "type": "break" if i in (0, len(waypoints) - 1) else "through"}
                for i, w in enumerate(waypoints)
            ],
            "costing": "truck",
            "costing_options": {
                "truck": {
                    "weight": round(truck.gross_lb * LB_TO_TONNE, 2),
                    "height": round(truck.height_ft * FT_TO_M, 2),
                    "hazmat": truck.hazmat,
                }
            },
            "directions_type": "maneuvers",  # times without the turn-by-turn text
            "units": "miles",
        }
        if alternatives and len(waypoints) == 2:
            body["alternates"] = alternatives
        resp = await fetch(
            self.name, "POST", self._url, attempts=1, timeout=TIMEOUT_S, json=body, headers=self._headers
        )
        if not resp.is_success:
            if _error_code(resp) in NO_ROUTE_CODES:
                return []
            raise UpstreamError(self.name, _error_text(resp), resp.status_code)
        data = json_or_error(self.name, resp)
        trips = [data["trip"]] + [a["trip"] for a in data.get("alternates", [])]
        return [self._parse(t) for t in trips]

    def _parse(self, trip: dict[str, Any]) -> RouteCandidate:
        parts: list[np.ndarray] = []
        anchor_idx: list[int] = []
        anchor_s: list[float] = []
        offset, elapsed = 0, 0.0
        for leg in trip["legs"]:
            shape = decode_polyline6(leg["shape"])
            skip = 1 if parts else 0  # each leg starts where the last one ended
            parts.append(shape[skip:])
            for m in leg["maneuvers"]:
                elapsed += float(m.get("time", 0.0))
                anchor_idx.append(max(offset + int(m["end_shape_index"]) - skip, 0))
                anchor_s.append(elapsed)
            offset += len(shape) - skip
        coords = np.concatenate(parts)
        anchor_idx = [min(i, len(coords) - 1) for i in anchor_idx]
        return RouteCandidate(coords, times_from_anchors(coords, anchor_idx, anchor_s), self.name, self.truck_aware)


def _error_code(resp: httpx.Response) -> int | None:
    try:
        code = resp.json().get("error_code")
    except (ValueError, AttributeError):
        return None
    return code if isinstance(code, int) else None


def _error_text(resp: httpx.Response) -> str:
    try:
        return str(resp.json().get("error") or resp.text[:200])
    except ValueError:
        return str(resp.text[:200])
