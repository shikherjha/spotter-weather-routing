"""Place search for the origin/destination inputs.

Photon (komoot) is free and built for type-ahead; TomTom fuzzy search is the fallback.
Nominatim is deliberately not used: its usage policy forbids autocomplete.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from config.env import get_env
from providers.http import UpstreamError, fetch, json_or_error

PHOTON_URL = "https://photon.komoot.io/api/"
TOMTOM_SEARCH_URL = "https://api.tomtom.com/search/2/search/{q}.json"
# Lower-48 + southern Canada + northern Mexico: where US truck trips run.
NA_BBOX = "-130,23,-60,55"

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Place:
    label: str
    lat: float
    lon: float


def _photon_label(props: dict[str, Any]) -> str:
    name = props.get("name") or " ".join(p for p in (props.get("housenumber"), props.get("street")) if p)
    region = props.get("state") or props.get("county")
    parts = [name, props.get("city") if props.get("city") != name else None, region, props.get("countrycode")]
    return ", ".join(p for p in parts if p)


async def search_places(query: str, limit: int = 6) -> list[Place]:
    q = query.strip()
    if len(q) < 2:
        return []
    try:
        return await _photon(q, limit)
    except UpstreamError as e:
        key = get_env().tomtom_api_key
        if key is None:
            raise
        log.info("photon failed (%s); falling back to TomTom search", e)
        return await _tomtom(q, limit, key.get_secret_value())


async def _photon(q: str, limit: int) -> list[Place]:
    params: dict[str, str | int] = {"q": q, "limit": limit, "lang": "en", "bbox": NA_BBOX}
    body = json_or_error("photon", await fetch("photon", "GET", PHOTON_URL, attempts=2, params=params))
    out = []
    for f in body.get("features", []):
        lon, lat = f["geometry"]["coordinates"]
        out.append(Place(_photon_label(f.get("properties", {})), float(lat), float(lon)))
    return out


async def _tomtom(q: str, limit: int, key: str) -> list[Place]:
    params: dict[str, str | int] = {
        "key": key,
        "limit": limit,
        "typeahead": "true",
        "countrySet": "US,CA,MX",
    }
    url = TOMTOM_SEARCH_URL.format(q=quote(q, safe=""))  # the query is a path segment
    body = json_or_error("tomtom", await fetch("tomtom", "GET", url, attempts=2, params=params))
    return [
        Place(r["address"].get("freeformAddress", q), r["position"]["lat"], r["position"]["lon"])
        for r in body.get("results", [])
    ]
