"""Departure-time advisor: re-score every route for later departures.

Uses the forecast already fetched for the checkpoints, so it costs zero API calls.
Assumes route geometry and moving times don't depend on departure hour (no traffic model).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from engine.evaluate import RoutePlan, evaluate
from engine.rules import WindBasis
from engine.scoring import Advice, RouteScore, rank, rank_key
from engine.weather import HOUR, WeatherGrid


@dataclass(frozen=True)
class DepartureOption:
    offset_h: int
    best: RouteScore
    advice: Advice


@dataclass(frozen=True)
class DepartureAdvice:
    options: list[DepartureOption]
    best_offset_h: int  # earliest departure whose best route ranks highest


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
    best = min(eligible, key=lambda o: (rank_key(o.best), o.offset_h))
    return DepartureAdvice(options, best.offset_h)
