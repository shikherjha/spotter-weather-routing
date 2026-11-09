"""The data the worker keeps locally: NBM fields, the forecast copy, stops at truck stops, Valhalla routes."""

import json
from pathlib import Path

import h3
import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from shapely.geometry import box

from engine.eta import HOUR, HosRules, StopKind, plan_stops
from providers.routing.valhalla import ValhallaRouting, decode_polyline6
from providers.weather import local, nbm

IDX = """1:0:d=2026110913:APCP:surface:0-1 hour acc fcst:prob >0.254:prob fcst 255/255
2:100:d=2026110913:APCP:surface:0-1 hour acc fcst:
3:200:d=2026110913:WIND:10 m above ground:1 hour fcst:
4:300:d=2026110913:WIND:10 m above ground:1 hour fcst:10% level
5:400:d=2026110913:WIND:30 m above ground:1 hour fcst:
6:500:d=2026110913:ASNOW:surface:47-53 hour acc fcst:
7:600:d=2026110913:TMP:2 m above ground:1 hour fcst:
"""


def test_idx_keeps_only_deterministic_fields_we_use() -> None:
    msgs = nbm.parse_idx(IDX, "u")
    got = [(m.var, m.start, m.end, m.hour, m.window) for m in msgs]
    assert got == [
        ("APCP", 100, 199, 1, 1),
        ("WIND", 200, 299, 1, 0),
        ("ASNOW", 500, 599, 53, 6),
        ("TMP", 600, None, 1, 0),
    ]


def test_three_hourly_wind_is_interpolated_and_ends_at_the_last_hour() -> None:
    hours = np.arange(1, 9)
    out = nbm._instant({3: np.array([3.0]), 6: np.array([6.0])}, 1, hours)
    assert np.isnan(out[0, :2]).all() and np.isnan(out[0, 6:]).all()
    assert out[0, 2:6].tolist() == [3.0, 4.0, 5.0, 6.0]


def test_a_longer_total_shares_only_what_its_hourly_totals_leave() -> None:
    hours = np.arange(1, 7)
    six = (6, 6, np.array([6.0, 4.0]))
    one = (2, 1, np.array([5.0, 5.0]))  # more than the 6 h total: nothing left, never negative
    out = nbm._totals([six, one], 2, hours)
    assert out[0].tolist() == pytest.approx([0.2, 5.0, 0.2, 0.2, 0.2, 0.2])
    assert out[1].tolist() == [0.0, 5.0, 0.0, 0.0, 0.0, 0.0]
    assert out[0].sum() == pytest.approx(6.0)


def test_a_six_hour_snow_total_falls_where_the_precipitation_does() -> None:
    hours = np.arange(1, 7)
    precip = np.array([[0.0, 0.0, 0.3, 0.1, 0.0, 0.0]], dtype=np.float32)
    snow = np.full((1, 6), np.nan, dtype=np.float32)
    snow[0, :] = 0.0
    nbm._snow_follows_precip(snow, [(6, 6, np.array([0.1], dtype=np.float32))], precip, hours)
    inches = 0.1 * nbm.M_TO_IN
    assert snow[0].tolist() == pytest.approx([0, 0, inches * 0.75, inches * 0.25, 0, 0], rel=1e-5)


def test_a_run_with_gaps_is_not_complete() -> None:
    full = list(range(1, 49)) + list(range(51, 170, 3))
    assert nbm.is_complete(full)
    assert not nbm.is_complete([h for h in full if h != 30])  # a missing hour inside the hourly part
    assert not nbm.is_complete([h for h in full if h not in (99, 102)])  # a 9 h hole later on
    assert not nbm.is_complete(list(range(1, 100)))  # doesn't reach far enough


def test_alternate_rows_are_flipped_back() -> None:
    values = np.array([0, 1, 2, 5, 4, 3, 6, 7, 8], dtype=np.float32)  # row 1 stored east to west
    assert nbm.unscan_alternate_rows(values, nx=3, ny=3).tolist() == [0, 1, 2, 3, 4, 5, 6, 7, 8]


def test_fallback_weather_lines_up_on_the_local_hourly_axis() -> None:
    src_times = np.array([0.0, 3600.0, 7200.0])
    dst_times = np.array([3600.0, 7200.0, 10800.0])
    out = local._align(src_times, np.array([[1.0, 2.0, 3.0]]), dst_times)
    assert out[0, :2].tolist() == [2.0, 3.0] and np.isnan(out[0, 2])


def test_rain_is_precipitation_minus_the_snows_water(tmp_path: Path) -> None:
    hours = np.arange(1, 2)
    inst = {
        "WIND": {1: np.array([1.0, 1.0, 1.0])},
        "GUST": {1: np.array([2.0, 2.0, 2.0])},
        "WDIR": {1: np.array([90.0, 90.0, 90.0])},
        "TMP": {1: np.array([280.0, 270.0, 280.0])},  # warm, freezing, warm
    }
    precip_mm = np.array([25.4, 25.4, 25.4])  # 1 in of water at each point
    snow_m = np.array([0.254, np.nan, np.nan])  # 10 in of snow at the first; no snow total elsewhere
    acc = {"APCP": [(1, 1, precip_mm)], "ASNOW": [(1, 1, snow_m)]}
    nbm._assemble(inst, acc, 3, hours, tmp_path / "f.npy")
    data = np.load(tmp_path / "f.npy").astype(float)
    rain, snow = data[:, 3, 0], data[:, 4, 0]
    assert rain == pytest.approx([0.0, 0.0, 1.0], abs=0.01)
    assert snow == pytest.approx([10.0, 10.0, 0.0], abs=0.05)


def _fake_run(root: Path, cells: list[str], run_s: int, values: np.ndarray) -> None:
    folder = root / "runs" / "2026110913"
    folder.mkdir(parents=True)
    ids = np.array(sorted(h3.str_to_int(c) for c in cells), dtype=np.uint64)
    np.save(folder / "cells.npy", ids)
    np.save(folder / "forecast.npy", values.astype(np.float16))
    hours = values.shape[2]
    (folder / "meta.json").write_text(json.dumps({"run": run_s, "first": run_s + 3600, "hours": hours}))
    (root / "current").write_text("2026110913")


@pytest.fixture
def _fresh_reader(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(local, "_loaded", None)
    monkeypatch.setattr(local, "_checked_at", 0.0)


@pytest.mark.usefixtures("_fresh_reader")
async def test_local_forecast_reads_any_resolution_from_its_res6_cells(tmp_path: Path) -> None:
    import time

    run_s = int(time.time() // HOUR * HOUR - 2 * HOUR)
    a, b = h3.latlng_to_cell(39.7, -105.0, 6), h3.latlng_to_cell(32.8, -96.8, 6)
    ordered = sorted([a, b], key=h3.str_to_int)
    values = np.zeros((2, 5, 4))
    values[:, 0, :] = [[10.0], [20.0]]  # wind by cell, in sorted order
    _fake_run(tmp_path, ordered, run_s, values)

    reader = local.LocalForecast.open(tmp_path)
    assert reader is not None
    finer = h3.cell_to_children(ordered[1], 7)[0]
    grid = await reader.grid([finer, ordered[0]])
    assert grid.wind_mph[:, 0].tolist() == [20.0, 10.0]
    assert grid.times[0] == run_s + HOUR


@pytest.mark.usefixtures("_fresh_reader")
def test_a_stale_copy_is_not_used(tmp_path: Path) -> None:
    _fake_run(tmp_path, [h3.latlng_to_cell(39.7, -105.0, 6)], 1_000_000_000, np.zeros((1, 5, 2)))
    assert local.LocalForecast.open(tmp_path) is None


def test_grid_map_finds_the_point_nearest_each_cell() -> None:
    g = {
        "Nx": 2345.0,
        "Ny": 1597.0,
        "latitudeOfFirstGridPointInDegrees": 19.229,
        "longitudeOfFirstGridPointInDegrees": 233.7234,
        "LoVInDegrees": 265.0,
        "Latin1InDegrees": 25.0,
        "Latin2InDegrees": 25.0,
        "DxInMetres": 2539.703,
        "DyInMetres": 2539.703,
        "radius": 6371200.0,
    }
    gm = nbm.build_grid_map(g, box(-105.1, 39.6, -104.9, 39.8))
    assert len(gm.cells) > 10
    assert gm.index.min() > 1_700_000 and gm.index.max() < 1_900_000  # Denver's rows, ~770 of 1597


def test_stops_move_back_to_the_last_place_before_the_limit() -> None:
    places = np.array([7.2, 7.9, 10.0, 18.5]) * HOUR
    stops = plan_stops(30 * HOUR, places=places)
    assert [(round(s.drive_s / HOUR, 1), s.kind, s.place) for s in stops[:3]] == [
        (7.9, StopKind.BREAK, 1),
        (10.0, StopKind.REST, 2),  # the 11-hour limit stays a rest even when taken early
        (18.0, StopKind.BREAK, None),  # nothing in the 90 minutes before the limit
    ]


def test_polyline6_decodes() -> None:
    assert decode_polyline6("_izlhA~rlgdF_{geC~ywl@_kwzCn`{nI").tolist() == [
        [38.5, -120.2],
        [40.7, -120.95],
        [43.252, -126.453],
    ]


def test_valhalla_times_follow_the_maneuvers() -> None:
    leg = {
        "shape": "_izlhA~rlgdF_{geC~ywl@_kwzCn`{nI",
        "maneuvers": [{"time": 100.0, "end_shape_index": 1}, {"time": 50.0, "end_shape_index": 2}],
    }
    route = ValhallaRouting("http://x")._parse({"legs": [leg]})
    assert route.cum_drive_s.tolist() == [0.0, 100.0, 150.0]


def test_zone_index_finds_every_zone_a_point_is_in() -> None:
    from providers.zones import Zone, ZoneIndex

    zs = [Zone("COC071", "CO", "Las Animas", "counties"), Zone("COZ088", "CO", "Trinidad Vicinity", "zones")]
    shapes = [box(-105.0, 37.0, -103.0, 37.6), box(-104.7, 37.0, -104.3, 37.3)]
    index = ZoneIndex(zs, shapes, box(-110, 30, -100, 40))
    inside, county_only, outside = index.at([(37.17, -104.5), (37.5, -103.5), (45.0, -90.0)])
    assert inside is not None and inside.zones == {"COC071", "COZ088"} and inside.county == "Las Animas County, CO"
    assert county_only is not None and county_only.zones == {"COC071"}
    assert outside is None


def test_alert_areas_use_the_polygon_else_the_zones_and_drop_statements() -> None:
    from providers import nws
    from providers.zones import Zone, ZoneIndex

    index = ZoneIndex([Zone("COZ088", "CO", "Trinidad", "zones")], [box(-105, 37, -104, 38)], box(-110, 30, -100, 40))

    def alert(event: str, ugc: set[str], polygon: object = None) -> nws.Alert:
        return nws.Alert(event, event, "Severe", "", "", "", "", "", 0.0, None, frozenset(ugc), polygon, None)  # type: ignore[arg-type]

    areas = nws.alert_areas(
        [
            alert("Winter Storm Warning", {"COZ088"}),
            alert("Wind Advisory", set(), box(-103, 37, -102, 38)),
            alert("Special Weather Statement", {"COZ088"}),
            alert("Gale Warning", {"ANZ330"}),  # marine: no land outline
        ],
        index,
    )
    assert [(f["properties"]["event"], f["properties"]["kind"]) for f in areas["features"]] == [
        ("Winter Storm Warning", "warning"),
        ("Wind Advisory", "advisory"),
    ]


def test_a_skipped_place_is_never_planned_for(monkeypatch: pytest.MonkeyPatch) -> None:
    from engine.geometry import Polyline
    from providers.osm_places import OnRoute, Place
    from trips import service

    stops = [OnRoute(Place("truck_stop", n, 35.0, -100.0 - i, 0), 100.0 * i, 0.1) for i, n in enumerate(["A", "B"])]
    monkeypatch.setattr(service.osm_places, "along", lambda line, kind, off: stops if kind == "truck_stop" else [])
    line = Polyline.from_coords(np.array([[35.0, -100.0], [35.0, -102.0]]))
    assert [p.place.name for p in service._stop_places(line, [])] == ["A", "B"]
    assert [p.place.name for p in service._stop_places(line, [(35.0, -101.0)])] == ["A"]


@settings(max_examples=200, deadline=None)
@given(
    total_h=st.floats(1, 60),
    places_h=st.lists(st.floats(0.1, 60), max_size=40),
    break_min=st.sampled_from([30.0, 150.0]),
)
def test_stops_at_places_never_break_the_hours_rules(total_h: float, places_h: list[float], break_min: float) -> None:
    rules = HosRules(break_min=break_min)
    places = np.array(sorted(places_h)) * HOUR
    stops = plan_stops(total_h * HOUR, rules, places)
    driven = shift_drive = shift_elapsed = 0.0
    for s in stops:
        leg = s.drive_s - driven
        assert leg <= rules.break_after_drive_h * HOUR + 1e-6  # never more than 8 h without stopping
        shift_drive += leg
        shift_elapsed += leg
        assert shift_drive <= rules.max_drive_h * HOUR + 1e-6
        assert shift_elapsed <= rules.window_h * HOUR + 1e-6
        if s.kind is StopKind.REST:
            shift_drive = shift_elapsed = 0.0
        else:
            shift_elapsed += s.duration_s
        driven = s.drive_s
    last = total_h * HOUR - driven
    assert last <= rules.break_after_drive_h * HOUR + 1e-6


def test_the_clock_places_stops_at_the_given_miles() -> None:
    from engine.eta import DriveProfile, TripClock

    miles = np.linspace(0, 1200, 121)
    profile = DriveProfile(miles, miles / 60.0 * HOUR)  # 60 mph
    clock = TripClock.build(0.0, profile, places_mi=np.array([300.0, 470.0, 610.0]))
    # A break at 470 (7.8 h in), the rest at 610 (the last place before the 11 h limit), then a break
    # 8 h later with no place near it.
    assert [round(m) for m in clock.stop_miles()] == [470, 610, 1090]


def test_a_weigh_station_mapped_once_per_direction_counts_once(monkeypatch: pytest.MonkeyPatch) -> None:
    from engine.geometry import Polyline
    from providers.osm_places import OnRoute, Place
    from trips import service

    found = [OnRoute(Place("weigh", "Weigh station", 35, -100, 0), m, 0.1) for m in (100.0, 101.1, 250.0)]
    monkeypatch.setattr(service.osm_places, "along", lambda line, kind, off: found)
    line = Polyline.from_coords(np.array([[35.0, -100.0], [35.0, -102.0]]))
    assert [w.mile for w in service._weigh_stations(line)] == [100.0, 250.0]
