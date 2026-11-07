import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from engine.sampling import place_checkpoints
from engine.units import HOUR
from engine.weather import Confidence, WeatherGrid, confidence, sample


def _grid() -> WeatherGrid:
    times = np.arange(0, 6) * HOUR  # 00:00 .. 05:00
    ones = np.ones((1, 6))
    return WeatherGrid(
        times=times,
        wind_mph=np.array([[10, 20, 30, 40, 50, 60]], dtype=float),
        gust_mph=np.array([[15, 25, 35, 45, 55, 65]], dtype=float),
        wind_dir_deg=ones * 270,
        rain_in_hr=np.array([[0.0, 0.1, 0.2, 0.3, 0.4, 0.5]]),
        snow_in_hr=ones * 0,
        issued_s=0.0,
    )


def test_accumulations_use_the_bucket_containing_t() -> None:
    g = _grid()
    s = sample(g, np.array([0, 0, 0]), np.array([1.25 * HOUR, 2 * HOUR, 2.0001 * HOUR]))
    # 01:15 lies in (01:00, 02:00] -> stamp 02:00; exactly 02:00 -> stamp 02:00; just after -> 03:00
    assert list(s.rain_in_hr) == pytest.approx([0.2, 0.2, 0.3])
    assert list(s.gust_mph) == pytest.approx([35, 35, 45])


def test_sustained_wind_is_interpolated() -> None:
    s = sample(_grid(), np.array([0]), np.array([1.25 * HOUR]))
    assert s.wind_mph[0] == pytest.approx(22.5)


def test_outside_forecast_is_invalid_not_clamped() -> None:
    s = sample(_grid(), np.array([0, 0]), np.array([-1.0, 5 * HOUR + 1]))
    assert not s.valid.any()
    assert s.conditions(0) is None
    assert np.isnan(s.wind_mph).all()


def test_grid_shape_is_validated() -> None:
    with pytest.raises(ValueError):
        WeatherGrid(np.arange(3.0), *(np.zeros((1, 2)),) * 5, issued_s=0.0)


@pytest.mark.parametrize(
    ("lead_h", "expected"),
    [(0, Confidence.HIGH), (24, Confidence.HIGH), (48, Confidence.MEDIUM), (100, Confidence.LOW)],
)
def test_confidence_by_lead_time(lead_h: float, expected: Confidence) -> None:
    assert confidence(lead_h * HOUR) is expected


# ---- checkpoints ----


def test_even_division() -> None:
    cp = place_checkpoints(100, 25)
    assert list(cp.miles) == [0, 25, 50, 75, 100]
    assert list(cp.weight_mi) == [12.5, 25, 25, 25, 12.5]


def test_remainder_gets_destination_checkpoint() -> None:
    cp = place_checkpoints(103, 25)
    assert list(cp.miles) == [0, 25, 50, 75, 100, 103]
    assert cp.weight_mi[-1] == pytest.approx(1.5)


def test_route_shorter_than_interval() -> None:
    cp = place_checkpoints(7, 10)
    assert list(cp.miles) == [0, 7]
    assert list(cp.weight_mi) == [3.5, 3.5]


def test_zero_length_route() -> None:
    assert len(place_checkpoints(0, 10)) == 1


@given(st.floats(min_value=0.01, max_value=3000), st.sampled_from([10, 25, 50]))
def test_weights_cover_the_route_exactly(length: float, interval: int) -> None:
    cp = place_checkpoints(length, interval)
    assert cp.weight_mi.sum() == pytest.approx(length, rel=1e-9)
    assert (cp.weight_mi >= 0).all()
    assert cp.miles[0] == 0 and cp.miles[-1] == pytest.approx(length)
    assert (np.diff(cp.miles) > 0).all()


def test_null_forecast_values_are_invalid() -> None:
    g = _grid()
    g.wind_mph[0, 3:] = np.nan
    s = sample(g, np.array([0, 0]), np.array([1.5 * HOUR, 4 * HOUR]))
    assert list(s.valid) == [True, False]
