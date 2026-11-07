import numpy as np
import pytest

from engine.eta import HOUR, DriveProfile, HosRules, StopKind, TripClock, plan_stops
from engine.geometry import Polyline, crosswind_mph, haversine_mi


def test_one_degree_of_latitude_is_about_69_miles() -> None:
    d = haversine_mi(np.array([40.0]), np.array([-100.0]), np.array([41.0]), np.array([-100.0]))
    assert d[0] == pytest.approx(69.09, abs=0.05)


def test_points_at_interpolates_and_clamps() -> None:
    line = Polyline.from_coords([(40.0, -100.0), (41.0, -100.0), (41.0, -99.0)])
    lat, lon = line.points_at(np.array([0.0, line.cum_mi[1] / 2, line.length_mi, line.length_mi + 50]))
    assert lat[0] == 40.0 and lon[0] == -100.0
    assert lat[1] == pytest.approx(40.5)
    assert (lat[2], lon[2]) == pytest.approx((41.0, -99.0))
    assert (lat[3], lon[3]) == pytest.approx((41.0, -99.0))


def test_bearings_and_crosswind() -> None:
    line = Polyline.from_coords([(40.0, -100.0), (41.0, -100.0)])  # heading north
    assert line.bearings_at(np.array([10.0]))[0] == pytest.approx(0.0, abs=1e-6)
    # wind from the west on a north-bound road is fully crosswind; from the north is head-on
    assert crosswind_mph(np.array([40.0]), np.array([270.0]), np.array([0.0]))[0] == pytest.approx(40.0)
    assert crosswind_mph(np.array([40.0]), np.array([0.0]), np.array([0.0]))[0] == pytest.approx(0.0, abs=1e-9)


def test_polyline_needs_two_points() -> None:
    with pytest.raises(ValueError):
        Polyline.from_coords([(1.0, 1.0)])


# ---- Hours of Service ----


def _kinds(stops: list) -> list[tuple[float, StopKind]]:
    return [(s.drive_s / HOUR, s.kind) for s in stops]


@pytest.mark.parametrize("hours", [0.5, 7.9, 8.0])
def test_no_stop_for_short_trips(hours: float) -> None:
    assert plan_stops(hours * HOUR) == []


def test_break_after_eight_hours() -> None:
    assert _kinds(plan_stops(9 * HOUR)) == [(8.0, StopKind.BREAK)]


def test_eleven_hours_needs_only_the_break() -> None:
    assert _kinds(plan_stops(11 * HOUR)) == [(8.0, StopKind.BREAK)]


def test_full_multiday_pattern() -> None:
    # 8 drive, 0.5 break, 3 drive, 10 rest, repeat
    assert _kinds(plan_stops(25 * HOUR)) == [
        (8.0, StopKind.BREAK),
        (11.0, StopKind.REST),
        (19.0, StopKind.BREAK),
        (22.0, StopKind.REST),
    ]


def test_fourteen_hour_window_binds_with_long_breaks() -> None:
    rules = HosRules(break_min=240)  # 8 h + 4 h break leaves 2 h in the 14 h window
    assert _kinds(plan_stops(12 * HOUR, rules)) == [(8.0, StopKind.BREAK), (10.0, StopKind.REST)]


def _straight_profile(miles: float, mph: float) -> DriveProfile:
    cum_mi = np.linspace(0.0, miles, 101)
    return DriveProfile(cum_mi, cum_mi / mph * HOUR)


def test_clock_adds_stop_time_after_each_stop() -> None:
    profile = _straight_profile(1200, 60)  # 20 h of driving
    clock = TripClock.build(departure_s=0.0, profile=profile)
    eta_h = clock.eta_s(np.array([480.0, 481.0, 660.0, 661.0])) / HOUR
    assert eta_h[0] == pytest.approx(8.0)  # arrives at the break location
    assert eta_h[1] == pytest.approx(8.0 + 1 / 60 + 0.5)  # after the 30 min break
    assert eta_h[2] == pytest.approx(11.5)  # arrives at the rest location
    assert eta_h[3] == pytest.approx(11.5 + 1 / 60 + 10)
    assert clock.total_elapsed_s / HOUR == pytest.approx(20 + 0.5 + 10 + 0.5)
    assert list(clock.stop_miles()) == pytest.approx([480.0, 660.0, 1140.0])


def test_hos_can_be_disabled() -> None:
    clock = TripClock.build(0.0, _straight_profile(1200, 60), hos=None)
    assert clock.stops == [] and clock.total_elapsed_s == pytest.approx(20 * HOUR)


def test_speed_cap_only_slows_fast_segments() -> None:
    cum_mi = np.array([0.0, 75.0, 105.0])
    cum_s = np.array([0.0, 1.0 * HOUR, 2.0 * HOUR])  # 75 mph then 30 mph
    capped = DriveProfile(cum_mi, cum_s).capped(65)
    assert np.diff(capped.cum_drive_s) / HOUR == pytest.approx([75 / 65, 1.0])


def test_shifted_clock_moves_every_eta() -> None:
    clock = TripClock.build(1000.0, _straight_profile(100, 50))
    assert clock.shifted(HOUR).eta_s(np.array([50.0]))[0] == pytest.approx(clock.eta_s(np.array([50.0]))[0] + HOUR)
