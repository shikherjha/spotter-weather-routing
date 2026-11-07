"""Departure-time advisor: re-score every route for later departures.

Uses the forecast already fetched for the checkpoints, so it costs zero API calls.
Assumes route geometry and moving times don't depend on departure hour (no traffic model).

Choosing *when* to leave differs from choosing a route in one way: waiting is not free.
Risk criteria are compared exactly as in `rank`, but the final tie-break is arrival time
(wait + trip), so "leave 13 h later to save 30 min on the road" can never win.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from engine.evaluate import RoutePlan, evaluate
from engine.rules import WindBasis
from engine.scoring import CRITERIA, Advice, RouteScore, rank
from engine.weather import HOUR, WeatherGrid


@dataclass(frozen=True)
class DepartureOption:
    offset_h: int
    best: RouteScore
    advice: Advice


@dataclass(frozen=True)
class DepartureAdvice:
    options: list[DepartureOption]
    best_offset_h: int  # safest departure; ties go to the earliest arrival


def _departure_key(o: DepartureOption) -> tuple[int, ...]:
    risk = tuple(c.bucket(o.best) for c in CRITERIA if c.key != "duration_s")
    arrival_min = round((o.offset_h * HOUR + o.best.duration_s) / 60)
    return (*risk, arrival_min, o.offset_h)


def sweep_departures(
    plans: Sequence[RoutePlan],
    grid: WeatherGrid,
    load_lb: float,
    hours: Sequence[int] = range(0, 25),
    wind_basis: WindBasis = WindBasis.SUSTAINED,
) -> DepartureAdvice:
    options = []
    for h in hours:
        scores = [evaluate(p, grid, load_lb, wind_basis, departure_offset_s=h * HOUR).score for p in plans]
        r = rank(scores)
        options.append(DepartureOption(h, r.recommended, r.advice))
    # Unknown (beyond-horizon) miles make a departure ineligible to be "best".
    eligible = [o for o in options if o.best.unknown_mi == 0] or options
    best = min(eligible, key=_departure_key)
    return DepartureAdvice(options, best.offset_h)
