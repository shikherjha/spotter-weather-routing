"""Route statistics and the brief's lexicographic recommendation.

Order of preference:
  0. fewest No Travel miles   (hard gate: the brief ranks only Severe/High, but a route
                               containing No Travel must never beat one without)
  0b. fewest miles beyond the forecast (only differs for departures days out: a route
                               must not win because its weather can't be seen yet)
  1. fewest Severe miles
  2. fewest High miles
  3. lowest distance-weighted average risk
  4. shortest travel time (wall-clock, including mandatory rest)

Each value is quantised to a stated tolerance before comparing, so "equal" is
well-defined and transitive, and floating-point noise can't flip a decision.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import StrEnum

import numpy as np

from engine.rules import Risk
from engine.units import FloatArray


@dataclass(frozen=True)
class RouteScore:
    route_id: str
    miles_by_level: tuple[float, ...]  # indexed by Risk
    unknown_mi: float  # beyond forecast horizon
    duration_s: float

    @property
    def known_mi(self) -> float:
        return float(sum(self.miles_by_level))

    @property
    def total_mi(self) -> float:
        return self.known_mi + self.unknown_mi

    @property
    def no_travel_mi(self) -> float:
        return self.miles_by_level[Risk.NO_TRAVEL]

    @property
    def severe_mi(self) -> float:
        return self.miles_by_level[Risk.SEVERE]

    @property
    def high_mi(self) -> float:
        return self.miles_by_level[Risk.HIGH]

    @property
    def avg_risk(self) -> float:
        """Distance-weighted mean level over miles with a forecast (0 = Low .. 4 = No Travel)."""
        if self.known_mi == 0:
            return 0.0
        return sum(int(lvl) * mi for lvl, mi in zip(Risk, self.miles_by_level, strict=True)) / self.known_mi


def score_route(route_id: str, levels: Sequence[Risk | None], weights_mi: FloatArray, duration_s: float) -> RouteScore:
    if len(levels) != len(weights_mi):
        raise ValueError("levels and weights must align")
    by_level = np.zeros(len(Risk))
    unknown = 0.0
    for lvl, w in zip(levels, weights_mi, strict=True):
        if lvl is None:
            unknown += float(w)
        else:
            by_level[lvl] += w
    return RouteScore(route_id, tuple(float(x) for x in by_level), unknown, float(duration_s))


@dataclass(frozen=True)
class Criterion:
    key: str
    label: str
    value: Callable[[RouteScore], float]
    tolerance: float
    unit: str

    def bucket(self, s: RouteScore) -> int:
        return round(self.value(s) / self.tolerance)


CRITERIA: tuple[Criterion, ...] = (
    Criterion("no_travel_mi", "No Travel miles", lambda s: s.no_travel_mi, 0.1, "mi"),
    Criterion("unknown_mi", "miles beyond the forecast", lambda s: s.unknown_mi, 1.0, "mi"),
    Criterion("severe_mi", "Severe miles", lambda s: s.severe_mi, 0.1, "mi"),
    Criterion("high_mi", "High miles", lambda s: s.high_mi, 0.1, "mi"),
    Criterion("avg_risk", "average risk", lambda s: s.avg_risk, 0.01, ""),
    Criterion("duration_s", "travel time", lambda s: s.duration_s, 60.0, "s"),
)


def rank_key(s: RouteScore) -> tuple[int, ...]:
    return tuple(c.bucket(s) for c in CRITERIA)


class Advice(StrEnum):
    GO = "go"  # recommended route has no Severe / No Travel miles
    CAUTION = "caution"  # best available route still has Severe miles
    DELAY = "delay"  # every route crosses No Travel conditions


@dataclass(frozen=True)
class Decision:
    """Why `winner` beat `loser`: the first criterion where they differ."""

    loser: str
    criterion: str | None  # None = tied on every criterion (kept input order)
    winner_value: float | None
    loser_value: float | None


@dataclass(frozen=True)
class Ranking:
    order: list[RouteScore]
    decisions: list[Decision]
    advice: Advice

    @property
    def recommended(self) -> RouteScore:
        return self.order[0]


def deciding_criterion(a: RouteScore, b: RouteScore) -> Criterion | None:
    for c in CRITERIA:
        if c.bucket(a) != c.bucket(b):
            return c
    return None


def rank(scores: Sequence[RouteScore]) -> Ranking:
    if not scores:
        raise ValueError("need at least one route")
    order = sorted(scores, key=rank_key)  # stable: full ties keep provider order
    best = order[0]
    decisions = []
    for other in order[1:]:
        c = deciding_criterion(best, other)
        decisions.append(
            Decision(other.route_id, c.key if c else None, c.value(best) if c else None, c.value(other) if c else None)
        )
    if best.no_travel_mi > 0:
        advice = Advice.DELAY
    elif best.severe_mi > 0:
        advice = Advice.CAUTION
    else:
        advice = Advice.GO
    return Ranking(order, decisions, advice)
