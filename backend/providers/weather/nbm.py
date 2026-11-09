"""NOAA's National Blend of Models (NBM, CONUS) straight from NOAA's public S3 bucket.

`sync` downloads the newest complete run and writes a compact copy that trips read locally:

  * Only the fields the risk rules read are fetched, by byte range: each GRIB2 file has a
    `.idx` listing where every field starts. About 750 MB per run instead of ~25 GB.
  * Each field is sampled at the centre of every H3 res-6 cell (~3 km across, close to NBM's
    2.5 km grid) and stored as one float16 array (cells, fields, hours) for a memory map.
  * NBM is hourly for 48 h; after that wind comes every 3 h, precipitation as 1 h totals every
    3rd hour plus 6 h totals, and snow as 6 h totals. Everything is put on one hourly axis: wind
    is interpolated, and each total is shared over the hours its shorter totals don't cover.
  * NBM's precipitation includes snow (as water). Rain is what's left after taking out the
    snow's water at 10:1; a 6 h snow total follows the hourly precipitation inside its window.
    Where there is no snow total, temperature decides rain or snow.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import shutil
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path

import eccodes
import h3
import numpy as np
from pyproj import Proj
from shapely.geometry.base import BaseGeometry

from engine.units import HOUR
from providers.http import UpstreamError, fetch

log = logging.getLogger(__name__)

PROVIDER = "NOAA NBM"
BUCKET = "https://noaa-nbm-grib2-pds.s3.amazonaws.com"
RES = 6
HORIZON_H = 168
ROWS = ("wind", "gust", "dir", "rain", "snow")
MIN_HOURS = 168  # a run counts as complete once it reaches this far...
MAX_GAP_H = 3  # ...with no gaps longer than NBM's 3-hourly steps...
HOURLY_UNTIL_H = 36  # ...and every hour up to here (all NBM runs are hourly this far)
SNOW_TO_WATER = 0.1  # 10 in of snow is about 1 in of water
FREEZING_C = 0.5
CONCURRENCY = 24
KEEP_RUNS = 2  # the previous run stays on disk for readers that still have it open

MS_TO_MPH = 2.236936
MM_TO_IN = 1 / 25.4
M_TO_IN = 39.37008

INSTANT = {
    "WIND": "10 m above ground",
    "GUST": "10 m above ground",
    "WDIR": "10 m above ground",
    "TMP": "2 m above ground",
}
_FCST = re.compile(r"^(\d+) hour fcst$")
_ACC = re.compile(r"^(\d+)-(\d+) hour acc fcst$")


@dataclass(frozen=True)
class Message:
    """One field in one forecast file: where its bytes are and what it holds."""

    url: str
    start: int
    end: int | None  # inclusive; None = to the end of the file
    var: str
    hour: int  # valid hour (instantaneous) or window end (totals)
    window: int = 0  # hours in a total; 0 = instantaneous


def parse_idx(text: str, url: str) -> list[Message]:
    """The fields we want from one `.idx` file (deterministic values only, no probabilities)."""
    lines = [ln.split(":") for ln in text.splitlines() if ln]
    out = []
    for n, parts in enumerate(lines):
        if len(parts) != 7 or parts[6]:
            continue  # percentiles, probabilities and std devs carry a 7th field
        var, level, fcst = parts[3], parts[4], parts[5]
        end = int(lines[n + 1][1]) - 1 if n + 1 < len(lines) else None
        start = int(parts[1])
        instant = INSTANT.get(var) == level
        if instant and (m := _FCST.match(fcst)):
            out.append(Message(url, start, end, var, int(m[1])))
        elif var in ("APCP", "ASNOW") and level == "surface" and (m := _ACC.match(fcst)):
            a, b = int(m[1]), int(m[2])
            out.append(Message(url, start, end, var, b, b - a))
    return out


@dataclass(frozen=True)
class GridMap:
    """H3 res-6 cells over the NBM domain and the grid point nearest each cell's centre."""

    cells: np.ndarray  # (N,) uint64, sorted
    index: np.ndarray  # (N,) int64 into the flattened GRIB values


def _grid_keys(handle: int) -> dict[str, float]:
    keys = (
        "Nx",
        "Ny",
        "latitudeOfFirstGridPointInDegrees",
        "longitudeOfFirstGridPointInDegrees",
        "LoVInDegrees",
        "Latin1InDegrees",
        "Latin2InDegrees",
        "DxInMetres",
        "DyInMetres",
        "radius",
    )
    return {k: float(eccodes.codes_get(handle, k)) for k in keys}


def build_grid_map(g: dict[str, float], area: BaseGeometry) -> GridMap:
    """Cells covering `area` (lon/lat), each mapped to the grid point nearest its centre."""
    nx, ny = int(g["Nx"]), int(g["Ny"])
    proj = Proj(
        proj="lcc",
        lat_1=g["Latin1InDegrees"],
        lat_2=g["Latin2InDegrees"],
        lat_0=g["Latin1InDegrees"],
        lon_0=g["LoVInDegrees"],
        R=g["radius"],
    )
    x0, y0 = proj(g["longitudeOfFirstGridPointInDegrees"], g["latitudeOfFirstGridPointInDegrees"])
    dx, dy = g["DxInMetres"], g["DyInMetres"]

    found = h3.h3shape_to_cells_experimental(h3.geo_to_h3shape(area), RES, contain="overlap")
    cells = np.array(sorted(h3.str_to_int(c) for c in found), dtype=np.uint64)
    centers = np.array([h3.cell_to_latlng(h3.int_to_str(int(c))) for c in cells])
    x, y = proj(centers[:, 1], centers[:, 0])
    i = np.rint((np.asarray(x) - x0) / dx).astype(np.int64)
    j = np.rint((np.asarray(y) - y0) / dy).astype(np.int64)
    inside = (i >= 0) & (i < nx) & (j >= 0) & (j < ny)
    return GridMap(cells[inside], (j * nx + i)[inside])  # rows run south to north, west to east


def _grid_map(handle: int, cache_dir: Path, area: BaseGeometry) -> GridMap:
    g = _grid_keys(handle)
    key = hashlib.sha1(json.dumps(g, sort_keys=True).encode() + area.wkb).hexdigest()[:12]
    path = cache_dir / f"grid-{key}.npz"
    if path.exists():
        with np.load(path) as z:
            return GridMap(z["cells"], z["index"])
    gm = build_grid_map(g, area)
    np.savez(path, cells=gm.cells, index=gm.index)
    return gm


async def _list_runs(day: str) -> list[str]:
    params = {"list-type": "2", "prefix": f"blend.{day}/", "delimiter": "/"}
    resp = await fetch(PROVIDER, "GET", f"{BUCKET}/", params=params)
    return sorted(re.findall(r"<Prefix>blend\.\d{8}/(\d{2})/</Prefix>", resp.text))


async def _forecast_hours(day: str, hour: str) -> list[int]:
    hours: list[int] = []
    token: str | None = None
    while True:
        params = {"list-type": "2", "prefix": f"blend.{day}/{hour}/core/blend.t{hour}z.core.f", "max-keys": "1000"}
        if token:
            params["continuation-token"] = token
        text = (await fetch(PROVIDER, "GET", f"{BUCKET}/", params=params)).text
        hours += [int(h) for h in re.findall(r"\.f(\d{3})\.co\.grib2\.idx</Key>", text)]
        if not (m := re.search(r"<NextContinuationToken>([^<]+)", text)):
            return sorted(set(hours))
        token = m[1]


def is_complete(hours: list[int]) -> bool:
    """Every hour to HOURLY_UNTIL_H, then no gap longer than NBM's 3-hourly steps, out to MIN_HOURS."""
    if not hours or hours[-1] < MIN_HOURS or set(range(1, HOURLY_UNTIL_H + 1)) - set(hours):
        return False
    return all(b - a <= MAX_GAP_H for a, b in pairwise(hours))


async def latest_run(now: datetime | None = None) -> tuple[datetime, list[int]] | None:
    """The newest complete run, with the forecast hours it has."""
    now = now or datetime.now(UTC)
    for day_offset in (0, 1):
        day = datetime.fromtimestamp(now.timestamp() - day_offset * 86400, UTC).strftime("%Y%m%d")
        for hour in reversed(await _list_runs(day)):
            hours = await _forecast_hours(day, hour)
            if is_complete(hours):
                return datetime.strptime(day + hour, "%Y%m%d%H").replace(tzinfo=UTC), hours
    return None


def _file_url(run: datetime, fh: int) -> str:
    return f"{BUCKET}/blend.{run:%Y%m%d}/{run:%H}/core/blend.t{run:%H}z.core.f{fh:03d}.co.grib2"


def _instant(series: dict[int, np.ndarray], n: int, hours: np.ndarray, nearest: bool = False) -> np.ndarray:
    """(n, H) values at `hours`, linear in time between known hours; NaN outside them."""
    out = np.full((n, len(hours)), np.nan, dtype=np.float32)
    known = np.array(sorted(series))
    if not len(known):
        return out
    stack = np.stack([series[h] for h in known], axis=1)
    hi = np.clip(np.searchsorted(known, hours), 1, len(known) - 1) if len(known) > 1 else np.zeros_like(hours)
    lo = np.maximum(hi - 1, 0)
    span = np.maximum(known[hi] - known[lo], 1)
    frac = np.clip((hours - known[lo]) / span, 0, 1).astype(np.float32)  # keeps the result float32
    ok = (hours >= known[0]) & (hours <= known[-1])
    if nearest:
        vals = np.where(frac < 0.5, stack[:, lo], stack[:, hi])
    else:
        vals = stack[:, lo] + frac * (stack[:, hi] - stack[:, lo])
    out[:, ok] = vals[:, ok]
    return out


def _totals(windows: list[tuple[int, int, np.ndarray]], n: int, hours: np.ndarray) -> np.ndarray:
    """(n, H) hourly amounts from (window end, window length, total).

    Shortest windows go first. A longer window shares only what its already-filled hours don't
    account for over the rest, so a 6 h total and the 1 h totals inside it add up to the 6 h total.
    """
    out = np.full((n, len(hours)), np.nan, dtype=np.float32)
    filled = np.zeros(len(hours), dtype=bool)
    col = {int(h): k for k, h in enumerate(hours)}
    for end, length, total in sorted(windows, key=lambda w: (w[1], w[0])):
        cols = [col[h] for h in range(end - length + 1, end + 1) if h in col]
        free = [c for c in cols if not filled[c]]
        if not free:
            continue
        known = [c for c in cols if filled[c]]
        rest = total - np.nansum(out[:, known], axis=1) if known else total
        out[:, free] = (np.maximum(rest, 0.0) / len(free))[:, None]
        filled[free] = True
    return out


def _snow_follows_precip(
    snow: np.ndarray, windows: list[tuple[int, int, np.ndarray]], precip: np.ndarray, hours: np.ndarray
) -> None:
    """Inside each multi-hour snow total, put the snow where the precipitation is (in place)."""
    col = {int(h): k for k, h in enumerate(hours)}
    for end, length, total in windows:
        if length == 1:
            continue
        cols = [col[h] for h in range(end - length + 1, end + 1) if h in col]
        if not cols:
            continue
        window_precip = np.nansum(precip[:, cols], axis=1)
        share = np.divide(
            precip[:, cols],
            window_precip[:, None],
            out=np.full((len(total), len(cols)), 1 / len(cols), dtype=np.float32),
            where=window_precip[:, None] > 0,
        )
        snow[:, cols] = np.where(np.isnan(snow[:, cols]), np.nan, total[:, None] * M_TO_IN * share)


async def _download(msg: Message, gate: asyncio.Semaphore) -> bytes:
    rng = f"bytes={msg.start}-{'' if msg.end is None else msg.end}"
    async with gate:
        resp = await fetch(PROVIDER, "GET", msg.url, headers={"Range": rng})
    if resp.status_code not in (200, 206):
        raise UpstreamError(PROVIDER, f"HTTP {resp.status_code}", resp.status_code)
    return resp.content


def unscan_alternate_rows(values: np.ndarray, nx: int, ny: int) -> np.ndarray:
    """GRIB "alternative row scanning": every other row runs east to west. Flip those (in place)."""
    rows = values.reshape(ny, nx)
    rows[1::2] = rows[1::2, ::-1].copy()
    return values


def _decode(raw: bytes) -> tuple[int, np.ndarray]:
    """Values in plain row order: west to east, rows south to north."""
    handle = eccodes.codes_new_from_message(raw)
    values = np.asarray(eccodes.codes_get_values(handle), dtype=np.float32)
    missing = float(eccodes.codes_get(handle, "missingValue"))
    values[values == missing] = np.nan
    if eccodes.codes_get(handle, "alternativeRowScanning") == 1:  # how NBM stores its grid
        unscan_alternate_rows(values, int(eccodes.codes_get(handle, "Nx")), int(eccodes.codes_get(handle, "Ny")))
    return handle, values


async def sync(root: Path, area: BaseGeometry) -> Path | None:
    """Download the newest complete run into `root` if it isn't there yet; returns its folder.

    `area` (lon/lat) is where cells are kept: the US, so ocean, Canada and Mexico aren't stored.
    """
    found = await latest_run()
    if found is None:
        log.warning("no complete NBM run found")
        return None
    run, fhs = found
    run_id = f"{run:%Y%m%d%H}"
    target = root / "runs" / run_id
    if (target / "meta.json").exists():
        _point_current(root, run_id)
        return target
    t0 = time.perf_counter()
    gate = asyncio.Semaphore(CONCURRENCY)
    wanted = [fh for fh in fhs if fh <= HORIZON_H]

    async def idx(fh: int) -> list[Message]:
        url = _file_url(run, fh)
        async with gate:
            resp = await fetch(PROVIDER, "GET", url + ".idx")
        if not resp.is_success:  # a missing hour would be interpolated over silently: try again next time
            raise UpstreamError(PROVIDER, f"no index for {run_id} f{fh:03d}", resp.status_code)
        return parse_idx(resp.text, url)

    async with asyncio.TaskGroup() as tg:
        parts = [tg.create_task(idx(fh)) for fh in wanted]
    messages = [m for part in parts for m in part.result()]
    if not messages:
        log.warning("NBM %s lists no fields we use", run_id)
        return None
    root.mkdir(parents=True, exist_ok=True)
    grid: GridMap | None = None
    inst: dict[str, dict[int, np.ndarray]] = defaultdict(dict)
    acc: dict[str, list[tuple[int, int, np.ndarray]]] = defaultdict(list)

    async def take(msg: Message) -> None:
        nonlocal grid
        raw = await _download(msg, gate)
        handle, values = await asyncio.to_thread(_decode, raw)
        try:
            if grid is None:
                grid = await asyncio.to_thread(_grid_map, handle, root, area)
        finally:
            eccodes.codes_release(handle)
        sampled = values[grid.index]
        if msg.window:
            acc[msg.var].append((msg.hour, msg.window, sampled))
        else:
            inst[msg.var][msg.hour] = sampled

    first, *rest = messages
    await take(first)  # builds the grid map once before the rest run in parallel
    async with asyncio.TaskGroup() as tg:  # one failed download cancels the others
        for m in rest:
            tg.create_task(take(m))
    assert grid is not None

    hours = np.arange(1, HORIZON_H + 1)
    n = len(grid.cells)
    tmp = root / "runs" / f".{run_id}.tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    await asyncio.to_thread(_assemble, inst, acc, n, hours, tmp / "forecast.npy")
    np.save(tmp / "cells.npy", grid.cells)
    meta = {"run": int(run.timestamp()), "first": int(run.timestamp() + HOUR), "hours": len(hours), "rows": ROWS}
    (tmp / "meta.json").write_text(json.dumps(meta))
    os.replace(tmp, target)
    _point_current(root, run_id)
    _prune(root)
    log.info("NBM %s synced: %d fields, %d cells, %.0f s", run_id, len(messages), n, time.perf_counter() - t0)
    return target


def _assemble(
    inst: dict[str, dict[int, np.ndarray]],
    acc: dict[str, list[tuple[int, int, np.ndarray]]],
    n: int,
    hours: np.ndarray,
    path: Path,
) -> None:
    """Write the (n, rows, hours) float16 array to `path`, one field at a time to keep memory down."""
    out = np.lib.format.open_memmap(path, mode="w+", dtype=np.float16, shape=(n, len(ROWS), len(hours)))
    out[:, ROWS.index("wind")] = _instant(inst["WIND"], n, hours) * MS_TO_MPH
    out[:, ROWS.index("gust")] = _instant(inst["GUST"], n, hours) * MS_TO_MPH
    out[:, ROWS.index("dir")] = _instant(inst["WDIR"], n, hours, nearest=True)
    precip = _totals(acc["APCP"], n, hours) * np.float32(MM_TO_IN)  # water, rain and snow together
    snow = _totals(acc["ASNOW"], n, hours) * np.float32(M_TO_IN)
    _snow_follows_precip(snow, acc["ASNOW"], precip, hours)
    cold = (_instant(inst["TMP"], n, hours) - np.float32(273.15)) <= FREEZING_C
    no_snow_total = np.isnan(snow) & ~np.isnan(precip)
    snow = np.where(no_snow_total, np.where(cold, precip / np.float32(SNOW_TO_WATER), 0.0), snow)
    rain = np.where(
        no_snow_total & cold, 0.0, np.maximum(precip - np.nan_to_num(snow) * np.float32(SNOW_TO_WATER), 0.0)
    )
    out[:, ROWS.index("rain")] = np.where(np.isnan(precip), np.nan, rain)
    out[:, ROWS.index("snow")] = snow
    out.flush()


def _point_current(root: Path, run_id: str) -> None:
    tmp = root / ".current.tmp"
    tmp.write_text(run_id)
    os.replace(tmp, root / "current")


def _prune(root: Path) -> None:
    runs = sorted(p for p in (root / "runs").iterdir() if p.is_dir() and not p.name.startswith("."))
    for old in runs[:-KEEP_RUNS]:
        shutil.rmtree(old, ignore_errors=True)
