"""TomTom Routing v1 in truck mode.

`extendedRouteRepresentation=travelTime,distance` returns a `progress` list of
(pointIndex, cumulative seconds) anchors, which we spread over every vertex.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import httpx
import numpy as np

from providers.http import UpstreamError, fetch, json_or_error
from providers.routing.base import LatLon, RouteCandidate, times_from_anchors

LB_TO_KG = 0.45359237
TARE_LB = 35_000  # empty tractor and 53 ft trailer; TomTom's vehicleWeight is the gross weight
BASE_URL = "https://api.tomtom.com/routing/1/calculateRoute"


class TomTomRouting:
    name = "tomtom"
    truck_aware = True

    def __init__(self, api_key: str) -> None:
        self._key = api_key

    async def routes(
        self, waypoints: Sequence[LatLon], depart_at: datetime, load_lb: float, alternatives: int
    ) -> list[RouteCandidate]:
        params: dict[str, Any] = {
            "key": self._key,
            "travelMode": "truck",
            "vehicleCommercial": "true",
            "vehicleWeight": round((TARE_LB + load_lb) * LB_TO_KG),
            "routeType": "fastest",
            "traffic": "false",  # departures are hours/days out; historic speeds are the honest choice
            "departAt": max(depart_at, datetime.now(UTC)).isoformat(timespec="seconds"),  # past times are rejected
            "routeRepresentation": "polyline",
            "extendedRouteRepresentation": ["distance", "travelTime"],
        }
        if alternatives and len(waypoints) == 2:
            params["maxAlternatives"] = alternatives
        url = f"{BASE_URL}/{':'.join(str(w) for w in waypoints)}/json"

        resp = await fetch(self.name, "GET", url, params=params)
        if not resp.is_success:
            raise UpstreamError(self.name, _error_text(resp), resp.status_code)
        body = json_or_error(self.name, resp)
        return [self._parse(r) for r in body.get("routes", [])]

    def _parse(self, route: dict[str, Any]) -> RouteCandidate:
        pts: list[list[float]] = []
        for i, leg in enumerate(route["legs"]):
            leg_pts = [[p["latitude"], p["longitude"]] for p in leg["points"]]
            pts.extend(leg_pts if i == 0 else leg_pts[1:])
        coords = np.asarray(pts, dtype=np.float64)
        progress = route.get("progress") or []
        if progress:
            idx = [min(p["pointIndex"], len(coords) - 1) for p in progress]
            secs = [p.get("travelTimeInSeconds", 0) for p in progress]
        else:
            idx, secs = [len(coords) - 1], [route["summary"]["travelTimeInSeconds"]]
        return RouteCandidate(coords, times_from_anchors(coords, idx, secs), self.name, self.truck_aware)


def _error_text(resp: httpx.Response) -> str:
    try:
        return str(resp.json().get("detailedError", {}).get("message") or resp.text[:200])
    except ValueError:
        return resp.text[:200]
