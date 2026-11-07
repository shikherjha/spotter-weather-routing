"""Route + clock + checkpoints + forecast + load -> per-checkpoint risk and a RouteScore."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from engine.eta import TripClock
from engine.geometry import Polyline, crosswind_mph
from engine.rules import Assessment, Conditions, Risk, WindBasis, classify
from engine.sampling import Checkpoints
from engine.scoring import RouteScore, score_route
from engine.units import FloatArray
from engine.weather import Confidence, IntArray, WeatherGrid, confidence, sample


@dataclass(frozen=True)
class RoutePlan:
    route_id: str
    line: Polyline
    clock: TripClock
    checkpoints: Checkpoints
    grid_index: IntArray  # WeatherGrid row holding each checkpoint's forecast

    def __post_init__(self) -> None:
        if len(self.grid_index) != len(self.checkpoints):
            raise ValueError("one grid row per checkpoint")


@dataclass(frozen=True)
class CheckpointResult:
    mile: float
    lat: float
    lon: float
    eta_s: float
    weight_mi: float
    conditions: Conditions | None
    assessment: Assessment | None
    crosswind_mph: float | None
    confidence: Confidence

    @property
    def level(self) -> Risk | None:
        return self.assessment.level if self.assessment else None


@dataclass(frozen=True)
class RouteEvaluation:
    plan: RoutePlan
    checkpoints: list[CheckpointResult]
    score: RouteScore


def evaluate(
    plan: RoutePlan,
    grid: WeatherGrid,
    load_lb: float,
    wind_basis: WindBasis = WindBasis.SUSTAINED,
    departure_offset_s: float = 0.0,
) -> RouteEvaluation:
    cp = plan.checkpoints
    clock = plan.clock.shifted(departure_offset_s) if departure_offset_s else plan.clock
    etas = clock.eta_s(cp.miles)
    s = sample(grid, plan.grid_index, etas)
    lats, lons = plan.line.points_at(cp.miles)
    xwind: FloatArray = crosswind_mph(s.wind_mph, s.wind_dir_deg, plan.line.bearings_at(cp.miles))

    results: list[CheckpointResult] = []
    for i in range(len(cp)):
        cond = s.conditions(i)
        results.append(
            CheckpointResult(
                mile=float(cp.miles[i]),
                lat=float(lats[i]),
                lon=float(lons[i]),
                eta_s=float(etas[i]),
                weight_mi=float(cp.weight_mi[i]),
                conditions=cond,
                assessment=classify(cond, load_lb, wind_basis) if cond else None,
                crosswind_mph=None if np.isnan(xwind[i]) else float(xwind[i]),
                confidence=confidence(float(etas[i]) - grid.issued_s),
            )
        )
    score = score_route(plan.route_id, [r.level for r in results], cp.weight_mi, clock.total_elapsed_s)
    return RouteEvaluation(plan, results, score)
