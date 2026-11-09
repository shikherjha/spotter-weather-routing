# /// script
# requires-python = ">=3.12"
# dependencies = ["osmium>=4.0"]
# ///
"""Pull the places a truck trip needs out of an OpenStreetMap extract (e.g. Geofabrik's us-latest).

    uv run scripts/extract_osm.py us-latest.osm.pbf backend/data/osm_places.csv.gz

Writes one row per place: kind, name, lat, lon, population.
  town         place=city|town, to name where a checkpoint is
  truck_stop   fuel stations that serve trucks (hgv tags or a truck-stop chain)
  rest_area    highway=rest_area|services
  weigh        weigh stations (amenity=weighbridge, highway=weigh_station)

Two passes: tags are filtered in C++, then only the nodes that outline the kept ways are read
back for their locations, so the US extract runs in minutes without a full node index.
"""

from __future__ import annotations

import csv
import gzip
import re
import sys
from collections.abc import Iterable

import osmium

TRUCK_STOP = re.compile(
    r"\b(love'?s|one9|pilot|flying j|travelcenters of america|ta|petro|sapp bros|bosselman|ambest|roady'?s|"
    r"road ranger|kenly 84|iowa 80|little america|town pump|stuckey'?s|truck stop|"
    r"travel (center|centre|plaza|stop))\b",
    re.IGNORECASE,
)
MERGE_DEG = 0.004  # ~400 m: a station mapped as both a point and its lot is one place
TAGS = [
    ("place", "city"),
    ("place", "town"),
    ("amenity", "fuel"),
    ("highway", "rest_area"),
    ("highway", "services"),
    ("amenity", "weighbridge"),
    ("highway", "weigh_station"),
]


def kind_of(tags: osmium.osm.TagList) -> str | None:
    place, amenity, highway = tags.get("place"), tags.get("amenity"), tags.get("highway")
    if place in ("city", "town"):
        return "town"
    if amenity == "weighbridge" or highway == "weigh_station":
        # CAT and similar scales sit inside truck stops for drivers to weigh themselves; not checkpoints.
        return None if re.search(r"\bcat\b|scale", tags.get("name", ""), re.IGNORECASE) else "weigh"
    label = " ".join(tags.get(k, "") for k in ("brand", "name", "operator"))
    trucks = tags.get("hgv") in ("yes", "designated") or tags.get("fuel:HGV_diesel") == "yes"
    if (amenity == "fuel" or highway == "services") and (trucks or TRUCK_STOP.search(label)):
        return "truck_stop"
    if highway in ("rest_area", "services"):
        return "rest_area"
    return None


def name_of(tags: osmium.osm.TagList, kind: str) -> str:
    name = tags.get("name") or tags.get("brand") or ""
    if kind == "weigh" and not name:
        return "Weigh station"
    if kind == "rest_area" and not name:
        return "Rest area"
    if kind == "truck_stop" and not name:
        return "Truck stop"
    return name


def population(tags: osmium.osm.TagList) -> int:
    digits = re.sub(r"[^\d]", "", tags.get("population", ""))
    return int(digits) if digits else 0


def main(src: str, dst: str) -> None:
    rows: list[tuple[str, str, float, float, int]] = []
    ways: list[tuple[str, str, int, list[int]]] = []
    proc = osmium.FileProcessor(src, osmium.osm.NODE | osmium.osm.WAY).with_filter(osmium.filter.TagFilter(*TAGS))
    for obj in proc:
        kind = kind_of(obj.tags)
        if kind is None or (kind == "town" and not obj.tags.get("name")):
            continue
        if obj.is_node():
            rows.append((kind, name_of(obj.tags, kind), obj.location.lat, obj.location.lon, population(obj.tags)))
        elif obj.is_way() and kind != "town":
            ways.append((kind, name_of(obj.tags, kind), 0, [n.ref for n in obj.nodes]))

    needed = {ref for *_, refs in ways for ref in refs}
    where: dict[int, tuple[float, float]] = {}
    for node in osmium.FileProcessor(src, osmium.osm.NODE).with_filter(osmium.filter.IdFilter(needed)):
        where[node.id] = (node.location.lat, node.location.lon)
    for kind, name, pop, refs in ways:
        pts = [where[r] for r in refs if r in where]
        if pts:
            rows.append((kind, name, sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts), pop))
    write(dst, merge(rows))


def merge(rows: list[tuple[str, str, float, float, int]]) -> list[tuple[str, str, float, float, int]]:
    """One row per place: drop a stop within MERGE_DEG of a kept one of the same kind (named rows first)."""
    kept: list[tuple[str, str, float, float, int]] = []
    seen: dict[tuple[str, int, int], list[tuple[float, float]]] = {}
    generic = {"Rest area", "Weigh station", "Truck stop"}
    for row in sorted(rows, key=lambda r: (r[0], r[1] in generic or not r[1], -r[4])):
        kind, _, lat, lon, _ = row
        if kind != "town":
            cell = (kind, int(lat / MERGE_DEG), int(lon / MERGE_DEG))
            near = [
                p
                for di in (-1, 0, 1)
                for dj in (-1, 0, 1)
                for p in seen.get((kind, cell[1] + di, cell[2] + dj), [])
            ]
            if any(abs(p[0] - lat) < MERGE_DEG and abs(p[1] - lon) < MERGE_DEG for p in near):
                continue
            seen.setdefault(cell, []).append((lat, lon))
        kept.append(row)
    return kept


def write(dst: str, rows: Iterable[tuple[str, str, float, float, int]]) -> None:
    with gzip.open(dst, "wt", newline="", encoding="utf-8") as f:
        out = csv.writer(f)
        out.writerow(["kind", "name", "lat", "lon", "population"])
        for kind, name, lat, lon, pop in sorted(rows):
            out.writerow([kind, name, f"{lat:.5f}", f"{lon:.5f}", pop])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
