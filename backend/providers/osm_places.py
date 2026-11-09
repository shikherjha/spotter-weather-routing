"""Towns, truck stops, rest areas and weigh stations from OpenStreetMap.

The data ships with the code: backend/data/osm_places.csv.gz, made by scripts/extract_osm.py
from Geofabrik's US extract. © OpenStreetMap contributors, ODbL.
"""

from __future__ import annotations

import csv
import gzip
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import shapely
from shapely.geometry import LineString

from engine.geometry import Polyline, haversine_mi
from providers.zones import ZoneIndex

DATA = Path(__file__).resolve().parents[1] / "data" / "osm_places.csv.gz"
DEG_PER_MI = 1 / 69.0  # a degree of latitude; longitude degrees are shorter, so searches over-cover
TOWN_MAX_MI = 25.0


@dataclass(frozen=True, slots=True)
class Place:
    kind: str  # town | truck_stop | rest_area | weigh
    name: str
    lat: float
    lon: float
    population: int


@dataclass(frozen=True, slots=True)
class OnRoute:
    place: Place
    mile: float  # where on the route it is
    off_mi: float  # how far from the road


class _Kind:
    def __init__(self, places: list[Place]) -> None:
        self.places = places
        self.tree = shapely.STRtree(shapely.points([p.lon for p in places], [p.lat for p in places]))


_lock = threading.Lock()
_kinds: dict[str, _Kind] | None = None
_town_states: list[str] | None = None


def _load() -> dict[str, _Kind]:
    global _kinds
    with _lock:
        if _kinds is None:
            by_kind: dict[str, list[Place]] = {}
            if DATA.exists():
                with gzip.open(DATA, "rt", encoding="utf-8") as f:
                    for row in csv.DictReader(f):
                        lat, lon, pop = float(row["lat"]), float(row["lon"]), int(row["population"])
                        by_kind.setdefault(row["kind"], []).append(Place(row["kind"], row["name"], lat, lon, pop))
            _kinds = {k: _Kind(v) for k, v in by_kind.items()}
        return _kinds


def nearest_towns(coords: Sequence[tuple[float, float]], zones: ZoneIndex | None) -> list[str | None]:
    """'Trinidad, CO' for the nearest town within TOWN_MAX_MI of each (lat, lon), else None.

    Without the zone outlines a town's state isn't known, and it's named alone ("Trinidad").
    """
    global _town_states
    towns = _load().get("town")
    if towns is None or not coords:
        return [None] * len(coords)
    if _town_states is None and zones is not None:
        found = zones.at([(p.lat, p.lon) for p in towns.places])
        _town_states = [z.state if z else "" for z in found]
    pts = shapely.points([lon for _, lon in coords], [lat for lat, _ in coords])
    idx = towns.tree.nearest(pts)
    out: list[str | None] = []
    for (lat, lon), k in zip(coords, idx.tolist(), strict=True):
        t = towns.places[k]
        far = float(haversine_mi(np.array([lat]), np.array([lon]), np.array([t.lat]), np.array([t.lon]))[0])
        state = _town_states[k] if _town_states else ""
        out.append((f"{t.name}, {state}" if state else t.name) if far <= TOWN_MAX_MI else None)
    return out


def along(line: Polyline, kind: str, max_off_mi: float) -> list[OnRoute]:
    """Places of one kind within `max_off_mi` of the route, in route order."""
    group = _load().get(kind)
    if group is None:
        return []
    geom = LineString(np.column_stack([line.lons, line.lats]))
    hits = group.tree.query(geom.buffer(max_off_mi * DEG_PER_MI * 1.5))
    if not len(hits):
        return []
    places = [group.places[i] for i in hits.tolist()]
    pts = shapely.points([p.lon for p in places], [p.lat for p in places])
    along_deg = shapely.line_locate_point(geom, pts)
    on_road = shapely.line_interpolate_point(geom, along_deg)
    lat = np.array([p.lat for p in places])
    lon = np.array([p.lon for p in places])
    off = haversine_mi(lat, lon, shapely.get_y(on_road), shapely.get_x(on_road))
    seg_deg = np.hypot(np.diff(line.lons), np.diff(line.lats))
    cum_deg = np.concatenate(([0.0], np.cumsum(seg_deg)))
    miles = np.interp(along_deg, cum_deg, line.cum_mi)
    out = [OnRoute(p, float(m), float(o)) for p, m, o in zip(places, miles, off, strict=True) if o <= max_off_mi]
    return sorted(out, key=lambda r: r.mile)


MAP_KINDS = ("truck_stop", "rest_area", "weigh")


def for_map() -> dict[str, list[tuple[float, float, str]]]:
    """Every truck stop, rest area and weigh station as (lat, lon, name), for the map's layers."""
    kinds = _load()
    return {k: [(p.lat, p.lon, p.name) for p in kinds[k].places] if k in kinds else [] for k in MAP_KINDS}
