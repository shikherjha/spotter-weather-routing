import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from engine.advisor import sweep_departures
from engine.corridor import build_corridor, route_signature, shared_fraction
from engine.eta import HOUR, DriveProfile, TripClock
from engine.evaluate import RoutePlan, evaluate
from engine.geometry import Polyline
from engine.rules import Risk
from engine.sampling import place_checkpoints
from engine.scoring import Advice, RouteScore, rank, score_route
from engine.weather import WeatherGrid


def _score(
    rid: str, nt: float = 0, severe: float = 0, high: float = 0, mod: float = 0, low: float = 100, hours: float = 10
) -> RouteScore:
    return RouteScore(rid, (low, mod, high, severe, nt), 0.0, hours * HOUR)


def test_each_criterion_in_priority_order() -> None:
    assert rank([_score("a", severe=5), _score("b", severe=1, high=90)]).recommended.route_id == "b"
    assert rank([_score("a", high=5), _score("b", high=1, mod=90, hours=30)]).recommended.route_id == "b"
    assert rank([_score("a", mod=50), _score("b", mod=10, hours=20)]).recommended.route_id == "b"
    assert rank([_score("a", hours=11), _score("b", hours=10)]).recommended.route_id == "b"


def test_no_travel_is_a_hard_gate_above_severe() -> None:
    r = rank([_score("a", nt=1), _score("b", severe=300)])
    assert r.recommended.route_id == "b"
    assert r.decisions[0].criterion == "no_travel_mi"
    assert r.advice is Advice.CAUTION


def test_all_routes_no_travel_means_delay() -> None:
    r = rank([_score("a", nt=10), _score("b", nt=3)])
    assert r.recommended.route_id == "b" and r.advice is Advice.DELAY


def test_tolerance_ties_fall_through_to_next_criterion() -> None:
    r = rank([_score("a", severe=10.02, hours=9), _score("b", severe=10.0, hours=8)])
    assert r.recommended.route_id == "b"
    assert r.decisions[0].criterion == "duration_s"


def test_full_tie_keeps_input_order() -> None:
    r = rank([_score("a"), _score("b")])
    assert r.recommended.route_id == "a" and r.decisions[0].criterion is None


def test_avg_risk_is_distance_weighted() -> None:
    s = score_route("x", [Risk.LOW, Risk.SEVERE, None], np.array([75.0, 25.0, 10.0]), 0)
    assert s.avg_risk == pytest.approx(0.75)  # (0*75 + 3*25) / 100 known miles
    assert s.unknown_mi == 10 and s.total_mi == 110


@given(st.lists(st.tuples(*[st.floats(0, 500)] * 4, st.floats(1, 100)), min_size=1, max_size=6), st.randoms())
def test_winner_does_not_depend_on_input_order(rows: list, rnd) -> None:  # type: ignore[no-untyped-def]
    scores = [_score(str(i), nt=r[0], severe=r[1], high=r[2], mod=r[3], hours=r[4]) for i, r in enumerate(rows)]
    shuffled = scores[:]
    rnd.shuffle(shuffled)
    from engine.scoring import rank_key

    assert rank_key(rank(scores).recommended) == rank_key(rank(shuffled).recommended)


# ---- end-to-end on synthetic data ----


def _storm_world() -> tuple[list[RoutePlan], WeatherGrid]:
    """Two 300-mile routes. Route 'north' has 50 mph wind for the first 6 forecast hours."""
    plans = []
    for rid, lat in (("north", 42.0), ("south", 40.0)):
        line = Polyline.from_coords([(lat, -104.0), (lat, -100.5)])
        profile = DriveProfile(line.cum_mi, line.cum_mi / 60 * HOUR)
        cp = place_checkpoints(line.length_mi, 25)
        plans.append(RoutePlan(rid, line, TripClock.build(0.0, profile), cp, np.arange(len(cp)) + len(plans) * 100))
    hours = 72
    wind = np.full((200, hours), 10.0)
    wind[:100, :6] = 50.0  # north route rows, first 6 hours
    zeros = np.zeros((200, hours))
    grid = WeatherGrid(np.arange(hours) * HOUR, wind, wind + 5, zeros + 270, zeros, zeros, issued_s=0.0)
    # 'south' is 10% slower so 'north' would win on time in calm weather
    south = plans[1]
    slow = DriveProfile(south.clock.profile.cum_mi, south.clock.profile.cum_drive_s * 1.1)
    plans[1] = RoutePlan("south", south.line, TripClock.build(0.0, slow), south.checkpoints, south.grid_index)
    return plans, grid


def test_heavy_truck_avoids_storm_route() -> None:
    plans, grid = _storm_world()
    scores = [evaluate(p, grid, load_lb=35_000).score for p in plans]
    r = rank(scores)
    assert r.recommended.route_id == "south"
    north = next(s for s in scores if s.route_id == "north")
    assert north.no_travel_mi > 0  # 45-54 mph and > 30,000 lb


def test_advisor_waits_only_when_waiting_buys_safety() -> None:
    plans, grid = _storm_world()
    # Leaving now, 'south' is clean: no reason to wait even though 'north' is faster later.
    assert sweep_departures(plans, grid, load_lb=35_000, hours=range(0, 12)).best_offset_h == 0

    # Storm over both routes for the first 6 h: the earliest clean departure wins, on the faster route.
    both = grid.wind_mph.copy()
    both[:, :6] = 50.0
    stormy = WeatherGrid(grid.times, both, both + 5, grid.wind_dir_deg, grid.rain_in_hr, grid.snow_in_hr, 0.0)
    advice = sweep_departures(plans, stormy, load_lb=35_000, hours=range(0, 12))
    assert advice.options[0].advice is Advice.DELAY
    assert advice.best_offset_h == 6
    assert advice.options[6].best.route_id == "north"


def test_checkpoint_results_carry_eta_and_reason() -> None:
    plans, grid = _storm_world()
    ev = evaluate(plans[0], grid, load_lb=35_000)
    first = ev.checkpoints[0]
    assert first.eta_s == 0.0 and first.level is Risk.NO_TRAVEL
    assert first.assessment is not None and first.assessment.load_escalated
    assert first.crosswind_mph == pytest.approx(0.0, abs=2.0)  # west wind on an east-bound road is a tailwind


# ---- corridor ----


def test_corridor_covers_route_with_render_and_sample_cells() -> None:
    line = Polyline.from_coords([(41.0, -105.0), (41.0, -104.0)])
    c = build_corridor([line], half_width_mi=10)
    assert len(c.cells) > len(c.sample_cells) > 0
    assert c.idw_weight.sum(axis=1) == pytest.approx(np.ones(len(c.cells)))
    values = np.arange(len(c.sample_cells), dtype=float)
    smoothed = c.smooth(values)
    assert smoothed.min() >= values.min() and smoothed.max() <= values.max()
    assert c.smooth(np.ones((len(c.sample_cells), 3))).shape == (len(c.cells), 3)


def test_route_signature_overlap() -> None:
    a = Polyline.from_coords([(41.0, -105.0), (41.0, -104.0)])
    b = Polyline.from_coords([(41.0, -105.0), (41.0, -104.5)])
    far = Polyline.from_coords([(35.0, -90.0), (35.0, -89.0)])
    sa, sb = route_signature(a), route_signature(b)
    assert shared_fraction(sa, sa) == 1.0
    assert shared_fraction(sb, sa) > 0.9  # b is a sub-path of a
    assert shared_fraction(route_signature(far), sa) == 0.0


def test_advisor_never_waits_just_to_shorten_the_drive() -> None:
    """Both departures are risk-free; the later one has a faster route but arrives later."""
    plans, grid = _storm_world()
    calm = WeatherGrid(
        grid.times,
        grid.wind_mph * 0 + 5,
        grid.gust_mph * 0 + 8,
        grid.wind_dir_deg,
        grid.rain_in_hr,
        grid.snow_in_hr,
        grid.issued_s,
    )
    advice = sweep_departures(plans, calm, load_lb=35_000, hours=range(0, 12))
    assert advice.best_offset_h == 0


def test_httpx_does_not_log_urls_with_keys() -> None:
    import logging

    assert logging.getLogger("httpx").getEffectiveLevel() >= logging.WARNING
