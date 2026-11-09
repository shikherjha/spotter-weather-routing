"""NWS forecast zones, counties and fire-weather zones, from the outline files NWS publishes.

Which zones a route point is in decides which warnings apply to it. Asking api.weather.gov
/points for every point is slow and rate-limited; with the outlines on disk it's an STRtree
query over ~11,000 polygons, milliseconds for a whole trip. NWS updates the files a few times
a year; `ensure` downloads the newest set listed on weather.gov.

Zone codes follow the alerts' UGC format: forecast and fire zones `COZ088`, counties `COC071`.
"""

from __future__ import annotations

import logging
import pickle
import re
import threading
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import shapefile
import shapely
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from providers.http import UpstreamError, fetch

log = logging.getLogger(__name__)

PROVIDER = "National Weather Service"
PAGES = {"zones": "PublicZones", "counties": "Counties", "fire": "FireZones"}
SITE = "https://www.weather.gov"
NOT_CONUS = frozenset({"AK", "HI", "PR", "VI", "GU", "AS", "MP"})
AREA_BUFFER_DEG = 0.25  # keeps border crossings and coastal roads inside the area
AREA_SIMPLIFY_DEG = 0.02


@dataclass(frozen=True, slots=True)
class Zone:
    ugc: str
    state: str
    name: str
    kind: str  # "zones" | "counties" | "fire"


@dataclass(frozen=True, slots=True)
class PointZones:
    zones: frozenset[str]
    county: str  # "Las Animas County, CO", for when no town is near
    state: str


# NWS names files by effective date with two-letter months: z_16ap26 = zones from 16 April 2026.
_MONTHS = dict(zip(["ja", "fe", "mr", "ap", "my", "jn", "jl", "au", "se", "oc", "no", "de"], range(1, 13), strict=True))
_FILE = re.compile(r'href="([^"]+?(\d{2})([a-z]{2})(\d{2})\.zip)"')


async def _latest_zip(page: str) -> str:
    """The newest outline file already in effect, from its page on weather.gov."""
    html = (await fetch(PROVIDER, "GET", f"{SITE}/gis/{page}")).text
    today = datetime.now(UTC).date()
    found: list[tuple[date, str]] = []
    for url, day, mon, yy in set(_FILE.findall(html)):
        if mon in _MONTHS and (when := date(2000 + int(yy), _MONTHS[mon], int(day))) <= today:
            found.append((when, url))
    if not found:
        raise UpstreamError(PROVIDER, f"no outline file listed on {page}")
    return SITE + max(found)[1]


async def ensure(root: Path) -> None:
    """Download the newest outline files into `root` if they aren't there, and build the index."""
    root.mkdir(parents=True, exist_ok=True)
    changed = False
    for kind, page in PAGES.items():
        url = await _latest_zip(page)
        target = root / f"{kind}-{url.rsplit('/', 1)[-1]}"
        if target.exists():
            continue
        resp = await fetch(PROVIDER, "GET", url, timeout=600)
        if not resp.is_success:
            raise UpstreamError(PROVIDER, f"HTTP {resp.status_code} for {kind} outlines", resp.status_code)
        target.write_bytes(resp.content)
        for old in root.glob(f"{kind}-*.zip"):
            if old != target:
                old.unlink()
        changed = True
    if changed or not (root / "index.pkl").exists():
        _build(root)


def _ugc(kind: str, rec: dict[str, str]) -> str:
    if kind == "counties":
        return f"{rec['STATE']}C{str(rec['FIPS'])[-3:]}"
    return f"{rec['STATE']}Z{rec['ZONE']}"


def _build(root: Path) -> None:
    zones: list[Zone] = []
    shapes: list[BaseGeometry] = []
    for kind in PAGES:
        (path,) = root.glob(f"{kind}-*.zip")
        reader = shapefile.Reader(str(path))
        for sr in reader.iterShapeRecords():
            rec = sr.record.as_dict()
            if not sr.shape.points:
                continue
            name = rec.get("COUNTYNAME") or rec.get("NAME") or ""
            zones.append(Zone(_ugc(kind, rec), str(rec["STATE"]), str(name), kind))
            shapes.append(shapely.make_valid(shape(sr.shape.__geo_interface__)))
    counties = [g for z, g in zip(zones, shapes, strict=True) if z.kind == "counties" and z.state not in NOT_CONUS]
    area = unary_union(counties).simplify(AREA_SIMPLIFY_DEG).buffer(AREA_BUFFER_DEG)
    tmp = root / "index.pkl.tmp"
    with tmp.open("wb") as f:
        pickle.dump({"zones": zones, "shapes": shapes, "conus": area}, f, protocol=pickle.HIGHEST_PROTOCOL)
    tmp.replace(root / "index.pkl")
    log.info("NWS outlines indexed: %d zones and counties", len(zones))


class ZoneIndex:
    def __init__(self, zones: list[Zone], shapes: list[BaseGeometry], conus: BaseGeometry) -> None:
        self._zones = zones
        self._tree = shapely.STRtree(shapes)
        self.conus = conus

    def at(self, coords: Sequence[tuple[float, float]]) -> list[PointZones | None]:
        """Zones, county and state for each (lat, lon); None outside every NWS zone (offshore, abroad)."""
        pts = shapely.points([lon for _, lon in coords], [lat for lat, _ in coords])
        point_idx, zone_idx = self._tree.query(pts, predicate="intersects")
        hits: list[list[Zone]] = [[] for _ in coords]
        for p, z in zip(point_idx.tolist(), zone_idx.tolist(), strict=True):
            hits[p].append(self._zones[z])
        out: list[PointZones | None] = []
        for zs in hits:
            county = next((z for z in zs if z.kind == "counties"), None)
            if not zs or county is None:
                out.append(None)
                continue
            out.append(PointZones(frozenset(z.ugc for z in zs), _county_label(county), county.state))
        return out


def _county_label(c: Zone) -> str:
    if "City" in c.name:
        return f"{c.name}, {c.state}"
    return f"{c.name} {'Parish' if c.state == 'LA' else 'County'}, {c.state}"


_lock = threading.Lock()
_index: dict[Path, ZoneIndex | None] = {}


def load(root: Path) -> ZoneIndex | None:
    """The index built by `ensure`, loaded once per process; None if it hasn't been built."""
    with _lock:
        if root not in _index or _index[root] is None:
            try:
                with (root / "index.pkl").open("rb") as f:
                    data = pickle.load(f)  # written by `_build`, never downloaded
                _index[root] = ZoneIndex(data["zones"], data["shapes"], data["conus"])
            except (OSError, pickle.UnpicklingError, KeyError):
                _index[root] = None
        return _index[root]
