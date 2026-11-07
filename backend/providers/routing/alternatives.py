"""Always try to return 3 genuinely different routes.

Providers only *try* to return alternatives (long trips often come back with 1-2,
or with near-duplicates). We dedupe by shared road (H3 res-7 signature) and, if
short, route through via points pushed sideways from the best route's midpoint.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from datetime import datetime

import numpy as np
from pyproj import Geod

from engine.corridor import route_signature, shared_fraction
from engine.geometry import METERS_PER_MILE, Polyline, haversine_mi, initial_bearing_deg
from providers.http import UpstreamError
from providers.routing.base import LatLon, RouteCandidate, RoutingProvider

log = logging.getLogger(__name__)
_GEOD = Geod(ellps="WGS84")

MAX_SHARED = 0.80  # reject a candidate that reuses >80% of an accepted route's road
MAX_STRETCH = 1.5  # reject a candidate >1.5x the fastest route's moving time
VIA_OFFSET_SHARE = 0.15  # via points sit this share of the trip's straight-line length off the axis...
VIA_OFFSET_MIN_MI = 20.0  # ...but at least this far, so short trips still get a real alternative
VIA_OFFSET_MAX_MI = 120.0


def _accept(cands: Sequence[RouteCandidate], accepted: list[RouteCandidate], want: int) -> None:
    sigs = [route_signature(Polyline.from_coords(r.coords)) for r in accepted]
    for c in cands:
        if len(accepted) >= want:
            return
        if accepted and c.duration_s > MAX_STRETCH * min(r.duration_s for r in accepted):
            continue
        sig = route_signature(Polyline.from_coords(c.coords))
        if any(shared_fraction(sig, s) > MAX_SHARED for s in sigs):
            continue
        accepted.append(c)
        sigs.append(sig)


def via_points(best: RouteCandidate, origin: LatLon, dest: LatLon) -> list[LatLon]:
    """Points offset perpendicular to the trip axis from the best route's midpoint."""
    line = Polyline.from_coords(best.coords)
    mid_lat, mid_lon = (float(a[0]) for a in line.points_at(np.array([line.length_mi / 2])))
    axis = float(
        initial_bearing_deg(np.array([origin.lat]), np.array([origin.lon]), np.array([dest.lat]), np.array([dest.lon]))[
            0
        ]
    )
    a, b = np.array([origin.lat, origin.lon]), np.array([dest.lat, dest.lon])
    straight_mi = float(haversine_mi(a[:1], a[1:], b[:1], b[1:])[0])
    base = min(max(VIA_OFFSET_SHARE * straight_mi, VIA_OFFSET_MIN_MI), VIA_OFFSET_MAX_MI)
    out = []
    for scale in (1.0, 2.0):
        for side in (90.0, -90.0):
            lon, lat, _ = _GEOD.fwd(mid_lon, mid_lat, axis + side, base * scale * METERS_PER_MILE)
            out.append(LatLon(lat, lon))
    return out


async def distinct_routes(
    provider: RoutingProvider, origin: LatLon, dest: LatLon, depart_at: datetime, load_lb: float, want: int = 3
) -> list[RouteCandidate]:
    first = await provider.routes([origin, dest], depart_at, load_lb, alternatives=want - 1)
    if not first:
        return []
    accepted: list[RouteCandidate] = []
    _accept(sorted(first, key=lambda r: r.duration_s), accepted, want)
    if len(accepted) >= want:
        return accepted

    vias = via_points(accepted[0], origin, dest)
    requests = [provider.routes([origin, v, dest], depart_at, load_lb, alternatives=0) for v in vias]
    if provider.name == "osrm":  # the public OSRM server allows about one request a second, so go in turn
        results: list[list[RouteCandidate] | BaseException] = []
        for req in requests:
            try:
                results.append(await req)
            except UpstreamError as e:
                results.append(e)
    else:
        results = await asyncio.gather(*requests, return_exceptions=True)
    extra = []
    for res in results:
        if isinstance(res, UpstreamError):
            log.info("via-point route failed: %s", res)  # UpstreamError text never includes the URL
            continue
        if isinstance(res, BaseException):
            raise res
        extra.extend(res)
    _accept(sorted(extra, key=lambda r: r.duration_s), accepted, want)
    return accepted
