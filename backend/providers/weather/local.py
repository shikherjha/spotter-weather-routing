"""Forecasts read from the NBM copy `nbm.sync` keeps on disk.

The copy (~380 MB) is read into memory once per forecast run, so a trip's cells (a few thousand
with the heatmap) are rows of one in-memory array: a fraction of a second and no network. A
memory map was tried first; on a network volume its scattered page reads took seconds per trip.
It's used for trips it covers; the few cells just over a border come from Open-Meteo's GFS and
are put on the same hourly axis.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import h3
import numpy as np

import providers.weather.nbm as nbm
from config.env import get_env
from engine.units import HOUR
from engine.weather import WeatherGrid
from providers.weather.openmeteo import FALLBACK_MODEL, OpenMeteoWeather

log = logging.getLogger(__name__)

MAX_AGE_H = 12  # an older copy means the sync has stopped; trips go back to Open-Meteo
RECHECK_S = 60


@dataclass(frozen=True)
class _Run:
    run_id: str
    run_s: float
    times: np.ndarray  # (H,) unix seconds
    cells: np.ndarray  # (N,) uint64, sorted
    data: np.ndarray  # (N, rows, H) float16


_lock = threading.Lock()
_loaded: _Run | None = None
_checked_at = 0.0


def _load(root: Path) -> _Run | None:
    """The current run, re-read at most once a minute and only when `current` changes."""
    global _loaded, _checked_at
    with _lock:
        if _loaded is not None and time.monotonic() - _checked_at < RECHECK_S:
            return _loaded
        _checked_at = time.monotonic()
        try:
            run_id = (root / "current").read_text().strip()
            if _loaded is None or _loaded.run_id != run_id:
                folder = root / "runs" / run_id
                meta = json.loads((folder / "meta.json").read_text())
                _loaded = _Run(
                    run_id=run_id,
                    run_s=float(meta["run"]),
                    times=meta["first"] + HOUR * np.arange(meta["hours"], dtype=np.float64),
                    cells=np.load(folder / "cells.npy"),
                    data=np.load(folder / "forecast.npy"),  # one sequential read per run
                )
        except (OSError, ValueError, KeyError) as e:
            log.info("no local NBM copy in %s (%s)", root, type(e).__name__)
            _loaded = None
        return _loaded


def _align(src_times: np.ndarray, values: np.ndarray, dst_times: np.ndarray) -> np.ndarray:
    """(N, H_src) hourly values -> (N, H_dst) on another hourly axis; NaN where `src` has no data."""
    out = np.full((values.shape[0], len(dst_times)), np.nan)
    pos = np.searchsorted(src_times, dst_times)
    ok = (pos < len(src_times)) & (src_times[np.minimum(pos, len(src_times) - 1)] == dst_times)
    out[:, ok] = values[:, pos[ok]]
    return out


class LocalForecast:
    name = "nbm-local"
    model = "ncep_nbm_conus"
    point_budget = 20_000  # rows on disk, not API calls
    sample_res = nbm.RES  # the heatmap can read its own cells

    def __init__(self, run: _Run) -> None:
        self._run = run

    @classmethod
    def open(cls, root: Path) -> LocalForecast | None:
        run = _load(root)
        if run is None or time.time() - run.run_s > MAX_AGE_H * HOUR:
            return None
        return cls(run)

    def coverage(self, points: Sequence[tuple[float, float]]) -> float:
        """Share of these (lat, lon) points the copy has forecasts for."""
        if not points:
            return 1.0
        cells = [h3.latlng_to_cell(lat, lon, nbm.RES) for lat, lon in points]
        return float(self._rows(cells)[1].mean())

    def _rows(self, cells: Sequence[str]) -> tuple[np.ndarray, np.ndarray]:
        run = self._run
        ids = np.array([h3.str_to_int(_at_res(c)) for c in cells], dtype=np.uint64)
        pos = np.minimum(np.searchsorted(run.cells, ids), len(run.cells) - 1)
        return pos, run.cells[pos] == ids

    def _read(self, cells: Sequence[str]) -> tuple[np.ndarray, np.ndarray]:
        pos, found = self._rows(cells)
        stack = np.full((len(cells), len(nbm.ROWS), len(self._run.times)), np.nan)
        stack[found] = self._run.data[pos[found]]
        return stack, found

    async def grid(self, cells: Sequence[str]) -> WeatherGrid:
        run = self._run
        stack, found = await asyncio.to_thread(self._read, cells)  # thousands of rows off disk
        missing = [c for c, f in zip(cells, found, strict=True) if not f]
        if missing:
            # Trips are only given this provider when it covers them, so this is a border's worth.
            other = await fallback_provider().grid(missing[: OpenMeteoWeather.point_budget])
            rows = (other.wind_mph, other.gust_mph, other.wind_dir_deg, other.rain_in_hr, other.snow_in_hr)
            filled = np.flatnonzero(~found)[: OpenMeteoWeather.point_budget]
            stack[filled] = np.stack([_align(other.times, r, run.times) for r in rows], axis=1)

        wind, gust, wdir, rain, snow = (stack[:, i, :] for i in range(len(nbm.ROWS)))
        return WeatherGrid(run.times, wind, gust, wdir, rain, snow, issued_s=run.run_s)


def fallback_provider() -> OpenMeteoWeather:
    env = get_env()
    key = env.open_meteo_api_key.get_secret_value() if env.open_meteo_api_key else None
    return OpenMeteoWeather(FALLBACK_MODEL, key or None)


def _at_res(cell: str) -> str:
    """The res-6 cell for any cell: its parent if finer, the one at its centre if coarser."""
    res = h3.get_resolution(cell)
    if res >= nbm.RES:
        return str(h3.cell_to_parent(cell, nbm.RES))
    lat, lon = h3.cell_to_latlng(cell)
    return str(h3.latlng_to_cell(lat, lon, nbm.RES))
