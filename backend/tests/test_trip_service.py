"""Full pipeline and HTTP API, offline: fake routing + fake weather with a known storm."""

import base64
import json
import time
from collections.abc import Sequence
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
import numpy as np
import pytest
from django.test import AsyncClient

from engine.units import HOUR
from engine.weather import WeatherGrid
from providers.nws import Alert, PointInfo
from providers.routing.base import LatLon, RouteCandidate
from trips import service
from trips import warnings as trip_warnings
from trips.schemas import PlaceIn, TripOut, TripRequest

DALLAS = PlaceIn(label="Dallas", lat=32.7767, lon=-96.797)
DENVER = PlaceIn(label="Denver", lat=39.7392, lon=-104.9903)
STORM_CENTER = ((DALLAS.lat + DENVER.lat) / 2, (DALLAS.lon + DENVER.lon) / 2)  # on the direct route
STORM_RADIUS_DEG = 0.8


class _ThreeRoutes:
    """A fast route through the storm and two slower ones skirting it to the south."""

    name, truck_aware = "fake", True

    async def routes(
        self, waypoints: Sequence[LatLon], depart_at: datetime, load_lb: float, alternatives: int
    ) -> list[RouteCandidate]:
        o, d = waypoints[0], waypoints[-1]
        out = []
        for bend, hours in ((0.0, 12.0), (-3.0, 14.0), (-5.0, 15.0)):
            t = np.linspace(0.0, 1.0, 400)[:, None]
            mid = np.array([(o.lat + d.lat) / 2 + bend, (o.lon + d.lon) / 2])
            a, b = np.array([o.lat, o.lon]), np.array([d.lat, d.lon])
            coords = (1 - t) ** 2 * a + 2 * (1 - t) * t * mid + t**2 * b  # quadratic Bezier
            out.append(RouteCandidate(coords, np.linspace(0, hours * HOUR, 400), "fake", True))
        return out


class _StormWeather:
    model = "fake"

    async def grid(self, cells: Sequence[str]) -> WeatherGrid:
        import h3

        run = int(time.time()) // 3600 * 3600 - 3 * 3600
        times = run + HOUR * np.arange(170, dtype=float)
        ll = np.array([h3.cell_to_latlng(c) for c in cells])
        dlat, dlon = ll[:, 0] - STORM_CENTER[0], (ll[:, 1] - STORM_CENTER[1]) * np.cos(np.radians(STORM_CENTER[0]))
        in_storm = np.hypot(dlat, dlon) < STORM_RADIUS_DEG
        wind = np.where(in_storm[:, None], 50.0, 8.0) * np.ones((1, len(times)))
        z = np.zeros_like(wind)
        return WeatherGrid(times, wind, wind + 5, z + 270, z, z, issued_s=float(run))


async def _fake_points(coords: list[tuple[float, float]], deadline_s: float) -> list[PointInfo | None]:
    # One forecast zone per whole degree of latitude, so tests can aim alerts at a band.
    return [PointInfo(frozenset({f"TXZ{int(lat):03d}"}), f"Town {int(lat)}, TX", "TX") for lat, _ in coords]


async def _no_alerts(states: list[str]) -> list[Alert]:
    return []


@pytest.fixture
def fakes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "get_routing_provider", lambda: _ThreeRoutes())
    monkeypatch.setattr(service, "get_weather_provider", lambda: _StormWeather())
    monkeypatch.setattr(service.nws, "points", _fake_points)
    monkeypatch.setattr(trip_warnings, "active_alerts", _no_alerts)


def _request(**kw: object) -> TripRequest:
    depart = datetime.now(ZoneInfo("America/Chicago")) + timedelta(hours=1)
    base: dict[str, object] = {
        "origin": DALLAS,
        "destination": DENVER,
        "departure_local": depart.replace(tzinfo=None, minute=0, second=0, microsecond=0),
        "load_lb": 35_000,
        "interval_mi": 25,
    }
    return TripRequest(**(base | kw))


@pytest.mark.usefixtures("fakes")
async def test_heavy_truck_is_routed_around_the_storm() -> None:
    trip = await service.plan_trip(_request())
    by_id = {r.id: r for r in trip.routes}
    assert len(trip.routes) == 3
    assert by_id["A"].score.no_travel_mi > 0  # 45-54 mph with > 30,000 lb
    rec = trip.recommendation
    assert rec.route_id != "A" and rec.advice == "go"
    assert any("No Travel miles" in r for r in rec.reasons)
    assert by_id["A"].lost_on is not None and by_id["A"].lost_on.criterion == "no_travel_mi"
    assert sorted(r.rank for r in trip.routes) == [1, 2, 3]


@pytest.mark.usefixtures("fakes")
async def test_light_truck_gets_severe_not_no_travel() -> None:
    trip = await service.plan_trip(_request(load_lb=20_000))
    a = next(r for r in trip.routes if r.id == "A")
    assert a.score.no_travel_mi == 0 and a.score.severe_mi > 0


@pytest.mark.usefixtures("fakes")
async def test_response_is_internally_consistent() -> None:
    trip = await service.plan_trip(_request())
    for r in trip.routes:
        assert sum(r.score.miles_by_level) + r.score.unknown_mi == pytest.approx(r.distance_mi, abs=0.1)
        assert r.segments[0].from_mi == 0 and r.segments[-1].to_mi == pytest.approx(r.distance_mi, abs=0.1)
        assert [c.eta for c in r.checkpoints] == sorted(c.eta for c in r.checkpoints)
        assert r.path_mi == sorted(r.path_mi) and r.path_mi[-1] == pytest.approx(r.distance_mi, abs=0.1)
        assert [s.kind for s in r.stops][:2] == ["break", "rest"]  # 12-15 h of driving
        assert r.duration_s > r.drive_s + 10 * HOUR
    h = trip.heatmap
    risk = np.frombuffer(base64.b64decode(h.risk), dtype=np.uint8)
    assert risk.size == len(h.cells) * h.hours and set(np.unique(risk)) <= {0, 1, 2, 3, 4, 255}
    assert 4 in risk  # the storm shows up as No Travel for this load
    assert h.resolution == 6
    assert all(c.place and c.place.startswith("Town ") for r in trip.routes for c in r.checkpoints)
    assert trip.warnings == [] and trip.warnings_status == "ok"


@pytest.mark.usefixtures("fakes")
async def test_a_broken_warnings_feed_never_fails_the_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    async def broken(states: list[str]) -> list[Alert]:
        raise ValueError("unexpected NWS payload")

    monkeypatch.setattr(trip_warnings, "active_alerts", broken)
    trip = await service.plan_trip(_request())
    assert trip.warnings_status == "unavailable" and len(trip.routes) == 3


@pytest.mark.usefixtures("fakes")
async def test_heatmap_uses_the_chosen_wind_reading() -> None:
    def peak(trip: TripOut) -> int:
        risk = np.frombuffer(base64.b64decode(trip.heatmap.risk), dtype=np.uint8)
        return int(risk[risk != 255].max())

    light = 25_000  # below the load rules, so only the wind bands matter
    sustained = await service.plan_trip(_request(load_lb=light))  # storm: 50 mph sustained, 55 gusts
    gusts = await service.plan_trip(_request(load_lb=light, wind_basis="gust"))
    assert (peak(sustained), peak(gusts)) == (3, 4)


@pytest.mark.usefixtures("fakes")
async def test_trip_survives_the_weather_service_being_down(monkeypatch: pytest.MonkeyPatch) -> None:
    async def down(coords: list[tuple[float, float]], deadline_s: float) -> list[PointInfo | None]:
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(service.nws, "points", down)
    trip = await service.plan_trip(_request())
    assert trip.warnings_status == "unavailable" and trip.routes
    assert all(c.place is None for r in trip.routes for c in r.checkpoints)


@pytest.mark.usefixtures("fakes")
async def test_past_departure_is_rejected() -> None:
    with pytest.raises(service.TripError, match="past"):
        await service.plan_trip(_request(departure_local=datetime(2020, 1, 1, 8)))


@pytest.mark.usefixtures("fakes")
async def test_http_api_round_trip() -> None:
    client = AsyncClient()
    body = json.loads(_request().model_dump_json())
    resp = await client.post("/api/trips", body, content_type="application/json")
    assert resp.status_code == 200
    assert "total;dur=" in resp["Server-Timing"]
    trip_id = resp.json()["id"]
    again = await client.get(f"/api/trips/{trip_id}")
    assert again.status_code == 200 and again.json()["id"] == trip_id
    assert (await client.get("/api/trips/nope")).status_code == 404


@pytest.mark.usefixtures("fakes")
async def test_http_api_validation_errors() -> None:
    client = AsyncClient()
    body = json.loads(_request().model_dump_json())
    bad_interval = await client.post("/api/trips", body | {"interval_mi": 15}, content_type="application/json")
    assert bad_interval.status_code == 422
    past = await client.post(
        "/api/trips", body | {"departure_local": "2020-01-01T08:00:00"}, content_type="application/json"
    )
    assert past.status_code == 422 and "past" in past.json()["detail"]
