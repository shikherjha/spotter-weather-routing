"""Official warnings: matching alerts to routes in space and time, the words shown, and Jev triage."""

from types import SimpleNamespace

import pytest
from shapely.geometry import box

import providers.jev
from providers.nws import Alert, PointInfo, parse_alert
from trips import schemas as s
from trips import warnings as w
from trips.triage import triage

T0 = 1_800_000_000
H = 3600


def _alert(**kw: object) -> Alert:
    base: dict[str, object] = {
        "id": "a1",
        "event": "Winter Storm Warning",
        "severity": "Severe",
        "headline": "",
        "nws_headline": "",
        "description": (
            "* WHAT...Heavy snow expected.\n\n* WHERE...Raton Pass.\n\n* IMPACTS...Travel could be\nvery difficult."
        ),
        "instruction": "",
        "area": "Raton Pass",
        "starts": T0,
        "ends": T0 + 10 * H,
        "ugc": frozenset({"COZ088"}),
        "polygon": None,
    }
    return Alert(**(base | kw))  # type: ignore[arg-type]


def _route(rid: str, n: int = 6) -> s.RouteOut:
    """Checkpoints every 25 mi, one hour apart, heading north from 36°N."""
    cps = [
        s.CheckpointOut(
            mile=25.0 * i, lat=36 + 0.3 * i, lon=-104.5, eta=T0 + i * H, tz="America/Denver",
            wind_mph=10, gust_mph=12, rain_in_hr=0, snow_in_hr=0, crosswind_mph=0, level=0,
            drivers=[], reason="", load_escalated=False, confidence="high",
        )
        for i in range(n)
    ]  # fmt: skip
    return s.RouteOut(
        id=rid, rank=1, recommended=True, provider="t", truck_aware=True, distance_mi=125, drive_s=1, duration_s=1,
        arrival=T0, path=[], path_mi=[], stops=[], checkpoints=cps, segments=[],
        score=s.ScoreOut(miles_by_level=[0] * 5, unknown_mi=0, no_travel_mi=0, severe_mi=0, high_mi=0, avg_risk=0),
        lost_on=None,
    )  # fmt: skip


def _zones(*codes_per_cp: str) -> list[PointInfo | None]:
    return [PointInfo(frozenset({c}), "Town, CO", "CO") for c in codes_per_cp]


async def test_alert_matches_the_stretch_of_route_inside_its_zone_while_it_is_in_effect() -> None:
    r = _route("B")
    zones = {"B": _zones("COZ087", "COZ088", "COZ088", "COZ088", "COZ089", "COZ089")}
    out = await w.route_warnings([r], zones, simulated=[_alert()])
    assert len(out) == 1
    hit = out[0].routes[0]
    assert (hit.route_id, hit.from_mi, hit.to_mi, hit.enter) == ("B", 25.0, 75.0, T0 + H)
    assert out[0].summary == "Heavy snow expected. Travel could be very difficult."


async def test_alert_that_ends_before_the_truck_arrives_is_ignored() -> None:
    zones = {"B": _zones(*["COZ088"] * 6)}
    late = _alert(starts=T0 - 5 * H, ends=T0 - H)
    assert await w.route_warnings([_route("B")], zones, simulated=[late]) == []


async def test_polygon_alerts_match_by_shape_not_county() -> None:
    zones = {"B": _zones(*["XXZ000"] * 6)}
    storm = _alert(ugc=frozenset(), polygon=box(-105, 36.5, -104, 37.0))  # covers checkpoints 2 and 3
    out = await w.route_warnings([_route("B")], zones, simulated=[storm])
    assert (out[0].routes[0].from_mi, out[0].routes[0].to_mi) == (50.0, 75.0)


async def test_warnings_that_do_not_affect_trucks_sort_last() -> None:
    zones = {"B": _zones(*["COZ088"] * 6)}
    frost = _alert(id="f", event="Frost Advisory", severity="Minor", description="* WHAT...Frost.")
    out = await w.route_warnings([_route("B")], zones, simulated=[frost, _alert()])
    assert [(x.event, x.relevant, x.triage) for x in out] == [
        ("Winter Storm Warning", True, "rules"),
        ("Frost Advisory", False, "rules"),
    ]


class _FakeJev:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    async def system_one(self, state: object, questions: object) -> SimpleNamespace:
        self.calls += 1
        if self.fail:
            raise TimeoutError
        return SimpleNamespace(
            nouls={"truck": SimpleNamespace(noul=0.93), "closure": SimpleNamespace(noul=0.81)},
            choices={"hazard": SimpleNamespace(choice="wind")},
        )


async def test_jev_answers_are_used_and_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    jev = _FakeJev()
    monkeypatch.setattr(providers.jev, "client", lambda: jev)
    a = _alert(event="High Wind Warning")
    first = (await triage([a]))[a.id]
    again = (await triage([a]))[a.id]
    assert first == again
    assert (first.by, first.hazard, first.relevant, first.road_closure, first.truck_risk) == (
        "jev",
        "wind",
        True,
        True,
        0.93,
    )
    assert jev.calls == 1


async def test_jev_failure_falls_back_to_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(providers.jev, "client", lambda: _FakeJev(fail=True))
    t = (await triage([_alert(event="Blizzard Warning")]))["a1"]
    assert (t.by, t.hazard, t.relevant) == ("rules", "snow_ice", True)


def test_wind_chill_is_about_cold_not_wind() -> None:
    from trips.triage import rules_triage

    assert rules_triage(_alert(event="Wind Chill Warning")).hazard == "temperature"


def test_plain_words_falls_back_to_the_headline_in_sentence_case() -> None:
    a = _alert(description="The National Weather Service has issued...", nws_headline="FLOOD WARNING REMAINS IN EFFECT")
    assert w.plain_words(a) == "Flood warning remains in effect."


def test_sampling_and_spreading_zone_lookups() -> None:
    assert w.sample_indices(9, 10) == [0, 2, 4, 6, 8]
    assert w.sample_indices(4, 25) == [0, 1, 2, 3]
    a, b = PointInfo(frozenset({"A"}), "A", "CO"), PointInfo(frozenset({"B"}), "B", "CO")
    assert w.spread([a, None, b], [0, 2, 4], 5) == [a, a, a, b, b]
    assert w.spread([None], [0], 2) == [None, None]


def test_parse_alert_reads_the_nws_geojson_shape() -> None:
    a = parse_alert(
        {
            "geometry": None,
            "properties": {
                "id": "urn:1",
                "event": "Wind Advisory",
                "severity": "Moderate",
                "onset": "2026-11-08T00:00:00-06:00",
                "ends": "2026-11-08T08:00:00-06:00",
                "geocode": {"UGC": ["KSZ029"]},
                "parameters": {"NWSheadline": ["WIND ADVISORY IN EFFECT"]},
                "areaDesc": "Logan",
            },
        }
    )
    assert a is not None and a.ugc == {"KSZ029"} and a.ends is not None and a.ends - a.starts == 8 * H
