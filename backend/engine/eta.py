"""When is the truck at mile X?

Two layers:
  1. DriveProfile — moving time only, from the routing provider's per-point travel
     times (optionally capped to a truck speed when the provider models cars).
  2. FMCSA Hours-of-Service — mandatory breaks and 10-hour rests turn moving time
     into wall-clock time. On multi-day trips this shifts later checkpoints by 10+ h,
     which is the difference between sampling the storm and missing it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

import numpy as np

from engine.units import HOUR, FloatArray

_EPS = 1e-6


@dataclass(frozen=True)
class DriveProfile:
    """Cumulative moving seconds at each polyline vertex (same length as cum_mi)."""

    cum_mi: FloatArray
    cum_drive_s: FloatArray

    def __post_init__(self) -> None:
        if self.cum_mi.shape != self.cum_drive_s.shape:
            raise ValueError("cum_mi and cum_drive_s must align")
        if np.any(np.diff(self.cum_drive_s) < -_EPS):
            raise ValueError("cum_drive_s must be non-decreasing")

    @property
    def total_drive_s(self) -> float:
        return float(self.cum_drive_s[-1])

    def drive_s_at(self, miles: FloatArray) -> FloatArray:
        return np.interp(miles, self.cum_mi, self.cum_drive_s)

    def miles_at(self, drive_s: FloatArray) -> FloatArray:
        return np.interp(drive_s, self.cum_drive_s, self.cum_mi)

    def capped(self, max_mph: float) -> DriveProfile:
        """Slow any segment faster than max_mph down to it (car routing -> truck)."""
        d_mi = np.diff(self.cum_mi)
        d_s = np.diff(self.cum_drive_s)
        floor_s = d_mi / max_mph * HOUR
        new = np.concatenate(([0.0], np.cumsum(np.maximum(d_s, floor_s))))
        return DriveProfile(self.cum_mi, new)


class StopKind(StrEnum):
    BREAK = "break"  # 30-minute break after 8 h driving
    REST = "rest"  # 10-hour off-duty reset


@dataclass(frozen=True)
class HosRules:
    max_drive_h: float = 11.0
    window_h: float = 14.0
    break_after_drive_h: float = 8.0
    break_min: float = 30.0
    reset_off_h: float = 10.0


DEFAULT_HOS = HosRules()


@dataclass(frozen=True)
class Stop:
    drive_s: float  # moving-time clock when the stop starts
    duration_s: float
    kind: StopKind


def plan_stops(total_drive_s: float, rules: HosRules = DEFAULT_HOS) -> list[Stop]:
    """Greedy HOS schedule for a driver starting fresh (fully rested) at departure.

    Drives as long as allowed, then takes the shortest stop that unlocks more driving.
    No stop is placed at the very end of the trip.
    """
    max_drive, window = rules.max_drive_h * HOUR, rules.window_h * HOUR
    break_after, brk, reset = rules.break_after_drive_h * HOUR, rules.break_min * 60, rules.reset_off_h * HOUR

    stops: list[Stop] = []
    driven = since_break = shift_drive = shift_elapsed = 0.0
    while True:
        room = min(break_after - since_break, max_drive - shift_drive, window - shift_elapsed)
        if total_drive_s - driven <= room + _EPS:
            return stops
        driven += room
        since_break += room
        shift_drive += room
        shift_elapsed += room
        shift_spent = shift_drive >= max_drive - _EPS or shift_elapsed + brk >= window - _EPS
        if shift_spent:
            stops.append(Stop(driven, reset, StopKind.REST))
            since_break = shift_drive = shift_elapsed = 0.0
        else:
            stops.append(Stop(driven, brk, StopKind.BREAK))
            since_break = 0.0
            shift_elapsed += brk


@dataclass(frozen=True)
class TripClock:
    """Maps miles along one route to wall-clock time (unix seconds, UTC)."""

    departure_s: float
    profile: DriveProfile
    stops: list[Stop] = field(default_factory=list)

    @classmethod
    def build(cls, departure_s: float, profile: DriveProfile, hos: HosRules | None = DEFAULT_HOS) -> TripClock:
        stops = plan_stops(profile.total_drive_s, hos) if hos else []
        return cls(departure_s, profile, stops)

    @property
    def _stop_starts(self) -> FloatArray:
        return np.array([s.drive_s for s in self.stops], dtype=np.float64)

    @property
    def _delay_before(self) -> FloatArray:
        # _delay_before[k] = total stop time of the first k stops
        return np.concatenate(([0.0], np.cumsum([s.duration_s for s in self.stops])))

    def elapsed_s_at_drive(self, drive_s: FloatArray) -> FloatArray:
        """Wall-clock seconds since departure. A point at a stop gets its *arrival* time."""
        n_before = np.searchsorted(self._stop_starts, drive_s, side="left")
        return np.asarray(drive_s) + self._delay_before[n_before]

    def eta_s(self, miles: FloatArray) -> FloatArray:
        return self.departure_s + self.elapsed_s_at_drive(self.profile.drive_s_at(miles))

    @property
    def total_elapsed_s(self) -> float:
        return self.profile.total_drive_s + float(self._delay_before[-1])

    def shifted(self, offset_s: float) -> TripClock:
        return TripClock(self.departure_s + offset_s, self.profile, self.stops)

    def stop_miles(self) -> FloatArray:
        return self.profile.miles_at(self._stop_starts)
