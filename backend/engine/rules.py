"""Risk classification: the brief's threshold table and load rules, as data.

Boundary semantics (the brief's bands share endpoints, so we pick one rule and test it):
  * Each threshold is the *lower* edge of its band and is inclusive: rain 0.25 -> High.
  * The top band follows the brief's wording literally: wind ">=55" is inclusive,
    rain ">1.00" and snow ">3.0" are strict, so rain 1.00 is Severe, not No Travel.
  * Load rules only ever raise a level; weights use strict ">" as written.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, StrEnum

import numpy as np
from numpy.typing import NDArray

from engine.units import FloatArray

# Inputs are rounded before comparison so float noise (0.24999999) can't flip a band.
_PRECISION = 4


class Risk(IntEnum):
    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self) -> str:
        return self.name.replace("_", " ").title()


class Factor(StrEnum):
    WIND = "wind"
    RAIN = "rain"
    SNOW = "snow"


class WindBasis(StrEnum):
    """Which wind value is compared against the wind thresholds."""

    SUSTAINED = "sustained"  # literal reading of the brief (default)
    GUST = "gust"
    WORST = "worst"  # max(sustained, gust)


@dataclass(frozen=True, slots=True)
class Threshold:
    value: float
    level: Risk
    inclusive: bool = True

    def reached_by(self, x: float) -> bool:
        return x >= self.value if self.inclusive else x > self.value


# Ascending lower edges per factor; anything below the first edge is Low.
THRESHOLDS: dict[Factor, tuple[Threshold, ...]] = {
    Factor.WIND: (  # mph
        Threshold(25, Risk.MODERATE),
        Threshold(35, Risk.HIGH),
        Threshold(45, Risk.SEVERE),
        Threshold(55, Risk.NO_TRAVEL),
    ),
    Factor.RAIN: (  # in/hr
        Threshold(0.10, Risk.MODERATE),
        Threshold(0.25, Risk.HIGH),
        Threshold(0.50, Risk.SEVERE),
        Threshold(1.00, Risk.NO_TRAVEL, inclusive=False),
    ),
    Factor.SNOW: (  # in/hr
        Threshold(0.5, Risk.MODERATE),
        Threshold(1.0, Risk.HIGH),
        Threshold(2.0, Risk.SEVERE),
        Threshold(3.0, Risk.NO_TRAVEL, inclusive=False),
    ),
}


@dataclass(frozen=True, slots=True)
class LoadRule:
    """If wind is within [wind_min, wind_max) and load > load_over_lb, raise to `level`."""

    wind_min: float
    wind_max: float
    load_over_lb: float
    level: Risk

    def applies(self, wind_mph: float, load_lb: float) -> bool:
        return self.wind_min <= wind_mph < self.wind_max and load_lb > self.load_over_lb


# ">=55 mph -> No Travel for any load" is already the wind table's top band.
LOAD_RULES: tuple[LoadRule, ...] = (
    LoadRule(45, 55, 30_000, Risk.NO_TRAVEL),
    LoadRule(35, 45, 40_000, Risk.SEVERE),
)


@dataclass(frozen=True, slots=True)
class Conditions:
    wind_mph: float
    rain_in_hr: float
    snow_in_hr: float
    gust_mph: float | None = None

    def wind_for(self, basis: WindBasis) -> float:
        if basis is WindBasis.SUSTAINED or self.gust_mph is None:
            return self.wind_mph
        if basis is WindBasis.GUST:
            return self.gust_mph
        return max(self.wind_mph, self.gust_mph)


@dataclass(frozen=True, slots=True)
class Assessment:
    level: Risk
    factor_levels: dict[Factor, Risk]
    drivers: tuple[Factor, ...]  # factors at the final level, in table order
    load_escalated: bool  # True when a load rule raised the level above the weather alone

    @property
    def reason(self) -> str:
        if self.level is Risk.LOW:
            return "Within safe limits"
        parts = [f.value for f in self.drivers]
        text = " + ".join(parts)
        return f"{text} with heavy load" if self.load_escalated else text


def level_for(factor: Factor, value: float) -> Risk:
    x = round(value, _PRECISION)
    level = Risk.LOW
    for t in THRESHOLDS[factor]:
        if t.reached_by(x):
            level = t.level
    return level


def load_level(wind_mph: float, load_lb: float) -> Risk:
    w = round(wind_mph, _PRECISION)
    return max(
        (rule.level for rule in LOAD_RULES if rule.applies(w, load_lb)),
        default=Risk.LOW,
    )


def classify(conditions: Conditions, load_lb: float, wind_basis: WindBasis = WindBasis.SUSTAINED) -> Assessment:
    if load_lb < 0:
        raise ValueError("load_lb must be non-negative")
    wind = conditions.wind_for(wind_basis)
    factor_levels = {
        Factor.WIND: level_for(Factor.WIND, wind),
        Factor.RAIN: level_for(Factor.RAIN, conditions.rain_in_hr),
        Factor.SNOW: level_for(Factor.SNOW, conditions.snow_in_hr),
    }
    weather = max(factor_levels.values())
    by_load = load_level(wind, load_lb)
    final = max(weather, by_load)
    escalated = by_load > weather
    if escalated:
        factor_levels[Factor.WIND] = by_load
    drivers = tuple(f for f, lvl in factor_levels.items() if lvl == final and final > Risk.LOW)
    return Assessment(final, factor_levels, drivers, escalated)


def levels_array(
    wind_mph: FloatArray, rain_in_hr: FloatArray, snow_in_hr: FloatArray, load_lb: float
) -> NDArray[np.int8]:
    """Vectorised `classify(...).level` for grids (heatmap cell x hour). NaN input -> -1."""
    wind = np.round(wind_mph, _PRECISION)
    out = np.zeros(np.shape(wind), dtype=np.int8)
    for factor, values in ((Factor.WIND, wind), (Factor.RAIN, rain_in_hr), (Factor.SNOW, snow_in_hr)):
        x = np.round(values, _PRECISION)
        for t in THRESHOLDS[factor]:
            hit = x >= t.value if t.inclusive else x > t.value
            out = np.where(hit, np.maximum(out, int(t.level)), out)
    for rule in LOAD_RULES:
        if load_lb > rule.load_over_lb:
            hit = (wind >= rule.wind_min) & (wind < rule.wind_max)
            out = np.where(hit, np.maximum(out, int(rule.level)), out)
    missing = np.isnan(wind_mph) | np.isnan(rain_in_hr) | np.isnan(snow_in_hr)
    return np.where(missing, -1, out).astype(np.int8)
