import pytest
from hypothesis import given
from hypothesis import strategies as st

from engine.rules import Conditions, Factor, Risk, WindBasis, classify, level_for, load_level

L, M, H, S, N = Risk.LOW, Risk.MODERATE, Risk.HIGH, Risk.SEVERE, Risk.NO_TRAVEL


@pytest.mark.parametrize(
    ("mph", "expected"),
    [(0, L), (24.99, L), (25, M), (34.99, M), (35, H), (44.99, H), (45, S), (54.99, S), (55, N), (80, N)],
)
def test_wind_bands(mph: float, expected: Risk) -> None:
    assert level_for(Factor.WIND, mph) is expected


@pytest.mark.parametrize(
    ("inches", "expected"),
    [(0, L), (0.0999, L), (0.10, M), (0.2499, M), (0.25, H), (0.4999, H), (0.50, S), (1.00, S), (1.0001, N)],
)
def test_rain_bands(inches: float, expected: Risk) -> None:
    assert level_for(Factor.RAIN, inches) is expected


@pytest.mark.parametrize(
    ("inches", "expected"),
    [(0, L), (0.49, L), (0.5, M), (0.99, M), (1.0, H), (1.99, H), (2.0, S), (3.0, S), (3.01, N)],
)
def test_snow_bands(inches: float, expected: Risk) -> None:
    assert level_for(Factor.SNOW, inches) is expected


def test_float_noise_does_not_flip_a_band() -> None:
    assert level_for(Factor.RAIN, 0.25 - 1e-9) is H
    assert level_for(Factor.WIND, 35 - 1e-7) is H


@pytest.mark.parametrize(
    ("mph", "load", "expected"),
    [
        (44.99, 50_000, S),  # 35-44 band, >40k -> Severe
        (35, 40_000, L),  # exactly 40,000 is not "> 40,000"
        (35, 40_001, S),
        (45, 30_000, L),
        (45, 30_001, N),  # 45-54 band, >30k -> No Travel
        (54.99, 80_000, N),
        (34.99, 80_000, L),  # below every load band
        (55, 0, L),  # >=55 is handled by the wind table, not a load rule
    ],
)
def test_load_rules(mph: float, load: float, expected: Risk) -> None:
    assert load_level(mph, load) is expected


def test_load_escalation_is_reported() -> None:
    a = classify(Conditions(wind_mph=40, rain_in_hr=0, snow_in_hr=0), load_lb=45_000)
    assert a.level is S
    assert a.load_escalated
    assert a.drivers == (Factor.WIND,)
    assert a.reason == "wind with heavy load"


def test_worst_factor_wins_and_ties_list_all_drivers() -> None:
    a = classify(Conditions(wind_mph=36, rain_in_hr=0.3, snow_in_hr=0.1), load_lb=10_000)
    assert a.level is H
    assert a.drivers == (Factor.WIND, Factor.RAIN)
    assert not a.load_escalated


def test_load_never_lowers_weather_level() -> None:
    a = classify(Conditions(wind_mph=40, rain_in_hr=0.6, snow_in_hr=0), load_lb=45_000)
    assert a.level is S
    assert not a.load_escalated  # rain alone already Severe


def test_low_has_no_drivers() -> None:
    a = classify(Conditions(10, 0, 0), 20_000)
    assert a.level is L and a.drivers == () and a.reason == "Within safe limits"


@pytest.mark.parametrize(("basis", "expected"), [(WindBasis.SUSTAINED, M), (WindBasis.GUST, S), (WindBasis.WORST, S)])
def test_wind_basis(basis: WindBasis, expected: Risk) -> None:
    c = Conditions(wind_mph=30, rain_in_hr=0, snow_in_hr=0, gust_mph=48)
    assert classify(c, 0, basis).level is expected


def test_negative_load_rejected() -> None:
    with pytest.raises(ValueError):
        classify(Conditions(0, 0, 0), -1)


finite = st.floats(min_value=0, max_value=200, allow_nan=False)
small = st.floats(min_value=0, max_value=6, allow_nan=False)
loads = st.floats(min_value=0, max_value=120_000, allow_nan=False)


@given(finite, finite, small, small, loads)
def test_more_wind_never_lowers_risk(w1: float, w2: float, rain: float, snow: float, load: float) -> None:
    lo, hi = sorted((w1, w2))
    assert classify(Conditions(lo, rain, snow), load).level <= classify(Conditions(hi, rain, snow), load).level


@given(finite, small, small, loads, loads)
def test_more_load_never_lowers_risk(wind: float, rain: float, snow: float, l1: float, l2: float) -> None:
    lo, hi = sorted((l1, l2))
    c = Conditions(wind, rain, snow)
    assert classify(c, lo).level <= classify(c, hi).level


@given(finite, small, small, small, small, loads)
def test_more_precip_never_lowers_risk(wind: float, r1: float, r2: float, s1: float, s2: float, load: float) -> None:
    (rl, rh), (sl, sh) = sorted((r1, r2)), sorted((s1, s2))
    assert classify(Conditions(wind, rl, sl), load).level <= classify(Conditions(wind, rh, sh), load).level


@given(finite, small, small, loads)
def test_vectorised_levels_match_scalar_classify(wind: float, rain: float, snow: float, load: float) -> None:
    import numpy as np

    from engine.rules import levels_array

    got = levels_array(np.array([wind]), np.array([rain]), np.array([snow]), load)[0]
    assert got == classify(Conditions(wind, rain, snow), load).level


def test_vectorised_levels_mark_missing() -> None:
    import numpy as np

    from engine.rules import levels_array

    assert levels_array(np.array([np.nan]), np.array([0.0]), np.array([0.0]), 0)[0] == -1
