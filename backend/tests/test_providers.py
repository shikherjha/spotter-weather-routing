from collections.abc import Sequence
from datetime import UTC, datetime

import h3
import httpx
import numpy as np
import pytest
import respx
from pydantic import SecretStr

from providers.http import UpstreamError
from providers.routing.alternatives import distinct_routes
from providers.routing.base import LatLon, RouteCandidate, Truck, times_from_anchors
from providers.routing.osrm import OsrmRouting
from providers.routing.tomtom import TomTomRouting
from providers.weather.openmeteo import HORIZON_H, OpenMeteoWeather, _parse_location

DEPART = datetime(2026, 11, 9, 12, tzinfo=UTC)


@respx.mock
async def test_upstream_failures_never_show_the_request_url() -> None:
    respx.get(url__startswith="https://api.tomtom.com/").mock(return_value=httpx.Response(503))
    with pytest.raises(UpstreamError) as err:
        await TomTomRouting("SECRET123").routes([LatLon(32.7, -96.8), LatLon(39.7, -105.0)], DEPART, Truck(40_000), 0)
    assert err.value.status == 503 and "SECRET123" not in str(err.value) and err.value.__cause__ is None


@respx.mock
async def test_place_search_escapes_the_query_in_the_url_path(monkeypatch: pytest.MonkeyPatch) -> None:
    from providers import places

    monkeypatch.setattr(places, "get_env", lambda: type("Env", (), {"tomtom_api_key": SecretStr("k")})())
    respx.get(url__startswith="https://photon.komoot.io/").mock(return_value=httpx.Response(500))
    tomtom = respx.get(url__startswith="https://api.tomtom.com/search/").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    await places.search_places("../routing/x?y")
    assert "/search/..%2Frouting%2Fx%3Fy.json" in str(tomtom.calls.last.request.url)


def test_times_from_anchors_spreads_by_distance() -> None:
    coords = np.array([[40.0, -100.0], [40.5, -100.0], [41.0, -100.0], [42.0, -100.0]])
    t = times_from_anchors(coords, [0, 3], [0.0, 400.0])
    assert t[0] == 0 and t[-1] == 400
    assert t[2] == pytest.approx(200.0, rel=1e-3)  # half the distance -> half the time


@respx.mock
async def test_tomtom_parses_multi_leg_route_without_duplicate_junction() -> None:
    body = {
        "routes": [
            {
                "summary": {"travelTimeInSeconds": 300},
                "legs": [
                    {"points": [{"latitude": 40.0, "longitude": -100.0}, {"latitude": 40.1, "longitude": -100.0}]},
                    {"points": [{"latitude": 40.1, "longitude": -100.0}, {"latitude": 40.2, "longitude": -100.0}]},
                ],
                "progress": [
                    {"pointIndex": 0, "travelTimeInSeconds": 0},
                    {"pointIndex": 2, "travelTimeInSeconds": 300},
                ],
            }
        ]
    }
    route = respx.get(url__startswith="https://api.tomtom.com/routing/1/calculateRoute/").mock(
        return_value=httpx.Response(200, json=body)
    )
    out = await TomTomRouting("k").routes(
        [LatLon(40, -100), LatLon(40.1, -100), LatLon(40.2, -100)], DEPART, Truck(40_000), 2
    )
    assert len(out) == 1 and out[0].coords.shape == (3, 2)
    assert list(out[0].cum_drive_s) == pytest.approx([0, 150, 300], rel=1e-3)
    params = route.calls.last.request.url.params
    # Gross weight: 35,000 lb empty truck + 40,000 lb load, in kg.
    assert params["travelMode"] == "truck" and params["vehicleWeight"] == "34019"
    assert "maxAlternatives" not in params  # not allowed with via points


@respx.mock
async def test_tomtom_bad_request_is_not_retried() -> None:
    route = respx.get(url__startswith="https://api.tomtom.com/").mock(
        return_value=httpx.Response(400, json={"detailedError": {"message": "bad point"}})
    )
    with pytest.raises(UpstreamError, match="bad point"):
        await TomTomRouting("k").routes([LatLon(0, 0), LatLon(1, 1)], DEPART, Truck(0), 2)
    assert route.call_count == 1


@respx.mock
async def test_osrm_parses_annotation_durations() -> None:
    body = {
        "code": "Ok",
        "routes": [
            {
                "duration": 30.0,
                "geometry": {"coordinates": [[-100.0, 40.0], [-100.0, 40.1], [-100.0, 40.2]]},
                "legs": [{"annotation": {"duration": [10.0, 20.0]}}],
            }
        ],
    }
    respx.get(url__startswith="https://router.project-osrm.org/").mock(return_value=httpx.Response(200, json=body))
    out = await OsrmRouting().routes([LatLon(40, -100), LatLon(40.2, -100)], DEPART, Truck(0), 2)
    assert list(out[0].cum_drive_s) == [0, 10, 30]
    assert out[0].coords[1].tolist() == [40.1, -100.0]
    assert not out[0].truck_aware


class _FakeRouting:
    """Returns the same straight route for direct requests; a route through the via point otherwise."""

    name, truck_aware = "fake", True

    def __init__(self) -> None:
        self.calls = 0

    async def routes(
        self, waypoints: Sequence[LatLon], depart_at: datetime, truck: Truck, alternatives: int
    ) -> list[RouteCandidate]:
        self.calls += 1
        pts = np.array([[w.lat, w.lon] for w in waypoints])
        dense = np.vstack([np.linspace(pts[i], pts[i + 1], 200) for i in range(len(pts) - 1)])
        cand = RouteCandidate(dense, np.linspace(0, 36_000, len(dense)), "fake", True)
        return [cand, cand] if len(waypoints) == 2 else [cand]


async def test_duplicates_are_removed_and_via_points_fill_to_three() -> None:
    fake = _FakeRouting()
    out = await distinct_routes(fake, LatLon(35.0, -100.0), LatLon(35.0, -94.0), DEPART, Truck(40_000))
    assert len(out) == 3
    assert fake.calls == 5  # 1 direct + 4 via-point attempts
    mids = sorted(float(r.coords[len(r.coords) // 2, 0]) for r in out)
    assert mids[0] < 35.0 - 0.1 and mids[-1] > 35.0 + 0.1  # one detour on each side of the axis


RUN = 1_800_000_000


def _om_location(n: int, wind: float = 10.0, null: bool = False) -> dict:
    def series(v: float) -> list[float | None]:
        return [None if null else v] * n

    return {
        "hourly": {
            "time": [RUN + 3600 * i for i in range(n)],
            "wind_speed_10m": series(wind),
            "wind_gusts_10m": series(wind + 5),
            "wind_direction_10m": series(270),
            "rain": series(0.1),
            "showers": series(0.05),
            "snowfall": series(0.0),
            "temperature_2m": series(2.0),
            "weather_code": series(61),
        }
    }


@respx.mock
async def test_open_meteo_rejects_a_forecast_on_a_different_time_axis() -> None:
    respx.get(url__regex=r".*/meta\.json").mock(
        return_value=httpx.Response(200, json={"last_run_initialisation_time": RUN})
    )
    shifted = _om_location(HORIZON_H + 1)
    shifted["hourly"]["time"] = [t + 3600 for t in shifted["hourly"]["time"]]
    respx.post("https://api.open-meteo.com/v1/forecast").mock(return_value=httpx.Response(200, json=[shifted]))
    with pytest.raises(UpstreamError, match="expected"):
        await OpenMeteoWeather("ncep_nbm_conus").grid([h3.latlng_to_cell(35.0, -100.0, 5)])


def test_parse_location_sums_rain_and_showers_and_keeps_nulls_as_nan() -> None:
    arr = _parse_location(_om_location(3))
    assert arr.shape == (7, 3) and arr[3, 0] == pytest.approx(0.15)
    assert np.isnan(_parse_location(_om_location(3, null=True))).all()


@respx.mock
async def test_open_meteo_batches_caches_and_falls_back_for_uncovered_cells() -> None:
    n = HORIZON_H + 1
    covered = h3.latlng_to_cell(39.7, -105.0, 5)
    uncovered = h3.latlng_to_cell(53.5, -113.5, 5)  # Edmonton: outside NBM CONUS
    respx.get(url__regex=r".*/meta\.json").mock(
        return_value=httpx.Response(200, json={"last_run_initialisation_time": RUN})
    )

    def forecast(request: httpx.Request) -> httpx.Response:
        form = dict(x.split("=", 1) for x in request.content.decode().split("&"))
        n_locs = len(form["latitude"].split("%2C"))
        if form["models"] == "gfs_seamless":
            return httpx.Response(200, json=[_om_location(n, wind=30)] * n_locs)
        return httpx.Response(200, json=[_om_location(n), _om_location(n, null=True)][:n_locs])

    route = respx.post("https://api.open-meteo.com/v1/forecast").mock(side_effect=forecast)
    wx = OpenMeteoWeather("ncep_nbm_conus")
    grid = await wx.grid([covered, uncovered])
    assert grid.times[0] == 1_800_000_000 and grid.times.shape == (n,)
    assert grid.wind_mph[0, 0] == 10 and grid.wind_mph[1, 0] == 30  # second cell from the GFS fallback
    assert route.call_count == 2

    await wx.grid([covered, uncovered])  # served from cache
    assert route.call_count == 2


class _Down:
    name = "valhalla"
    truck_aware = True

    def __init__(self, status: int | None) -> None:
        self.status = status

    async def routes(
        self, waypoints: Sequence[LatLon], depart_at: datetime, truck: Truck, alternatives: int
    ) -> list[RouteCandidate]:
        raise UpstreamError("valhalla", "down", self.status)


class _Backup(_Down):
    name = "tomtom"

    async def routes(
        self, waypoints: Sequence[LatLon], depart_at: datetime, truck: Truck, alternatives: int
    ) -> list[RouteCandidate]:
        return []


async def test_our_router_falls_back_to_tomtom_when_it_is_down_but_not_on_a_bad_request() -> None:
    from providers.routing import WithFallback

    args = ([LatLon(35, -100), LatLon(36, -100)], DEPART, Truck(0), 0)
    assert await WithFallback(_Down(503), _Backup(None)).routes(*args) == []
    assert await WithFallback(_Down(None), _Backup(None)).routes(*args) == []
    with pytest.raises(UpstreamError):
        await WithFallback(_Down(400), _Backup(None)).routes(*args)
