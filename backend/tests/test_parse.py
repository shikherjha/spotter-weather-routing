"""Typed trip -> form fields: exact parts by code, fuzzy timing by Jev (faked here)."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from providers.jev import Departure
from providers.places import Place
from trips import parse

CST = ZoneInfo("America/Chicago")
NOW = datetime(2026, 11, 7, 15, 20, tzinfo=CST)  # Saturday afternoon


@pytest.mark.parametrize(
    ("text", "origin", "destination"),
    [
        ("Dallas to Denver tomorrow at noon", "Dallas", "Denver"),
        ("from Chicago, IL to Salt Lake City first thing Monday", "Chicago, IL", "Salt Lake City"),
        ("need to get to Denver from Amarillo asap", "Amarillo", "Denver"),
        ("Houston - Atlanta at 6:30 pm", "Houston", "Atlanta"),
        ("Dallas to Fort Worth", "Dallas", "Fort Worth"),
    ],
)
def test_reads_the_two_places(text: str, origin: str, destination: str) -> None:
    p = parse.read_text(text)
    assert (p.origin, p.destination) == (origin, destination)


@pytest.mark.parametrize(
    ("text", "load"),
    [
        ("42k lbs of steel", 42000),
        ("38,000 lbs", 38000),
        ("hauling 21 tons", 42000),
        ("30k", 30000),
        ("on I-25 at 6", None),
    ],
)
def test_reads_the_load_and_ignores_bare_numbers(text: str, load: float | None) -> None:
    assert parse.read_text(text).load_lb == load


def test_reads_exact_clock_times_and_spacing() -> None:
    assert parse.read_text("at 6:30 pm, every 10 miles").clock == (18, 30)
    assert parse.read_text("leave at noon").clock == (12, 0)
    assert parse.read_text("at 12 am").clock == (0, 0)
    assert parse.read_text("every 10 miles").interval_mi == 10


def test_day_options_name_real_dates() -> None:
    days = parse.day_options(NOW)
    assert days["d0"] == "Today, Saturday, November 7"
    assert days["d2"] == "Monday, November 9"
    assert len(days) == 6


def test_jev_reading_becomes_a_wall_clock_time() -> None:
    sure = Departure("d1", 0.9, "h13", 0.9)
    assert parse.resolve_departure(sure, None, NOW) == (datetime(2026, 11, 8, 13, 0, tzinfo=CST), False)
    unsure = Departure("d1", 0.4, "h13", 0.9)
    assert parse.resolve_departure(unsure, None, NOW)[1] is True


def test_now_means_the_next_whole_hour() -> None:
    assert parse.resolve_departure(Departure("unstated", 1, "now", 1), None, NOW)[0] == datetime(
        2026, 11, 7, 16, 0, tzinfo=CST
    )


def test_a_time_already_past_today_means_tomorrow() -> None:
    d, unsure = parse.resolve_departure(Departure("unstated", 1, "unstated", 1), (6, 0), NOW)
    assert d == datetime(2026, 11, 8, 6, 0, tzinfo=CST) and not unsure


def test_a_day_without_a_time_is_left_for_the_driver() -> None:
    assert parse.resolve_departure(Departure("d2", 0.9, "unstated", 0.9), None, NOW) == (None, True)


def test_rules_fill_what_jev_left_unstated_and_flag_it() -> None:
    merged = parse.combine(Departure("d2", 0.9, "unstated", 0.8), parse.rules_departure("first thing monday", NOW))
    assert merged == Departure("d2", 0.9, "h07", 0.0)


async def test_parse_trip_end_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    async def places(q: str, limit: int = 6) -> list[Place]:
        return {
            "Dallas": [Place("Dallas, Texas, US", 32.78, -96.8)],
            "Denver": [Place("Denver, Colorado, US", 39.74, -104.99)],
        }[q]

    async def jev(text: str, days: dict[str, str]) -> Departure:
        assert "d1" in days
        return Departure("d1", 0.95, "h13", 0.9)

    monkeypatch.setattr(parse, "search_places", places)
    monkeypatch.setattr(parse, "read_departure", jev)
    out = await parse.parse_trip("Dallas to Denver tomorrow after lunch, 42k lbs", "Asia/Kolkata")
    assert out.origin and out.origin.label == "Dallas, Texas, US"
    assert out.destination and out.destination.label == "Denver, Colorado, US"
    assert out.load_lb == 42000 and out.read_by == "jev" and out.unsure == []
    assert out.departure_local and out.departure_local.endswith("T13:00")  # 1 PM in Dallas, not in Kolkata


async def test_parse_falls_back_to_rules_without_jev(monkeypatch: pytest.MonkeyPatch) -> None:
    async def nowhere(q: str, limit: int = 6) -> list[Place]:
        return []

    monkeypatch.setattr(parse, "search_places", nowhere)
    out = await parse.parse_trip("Springfield to Nowhereville tomorrow morning", "America/Chicago")
    assert out.read_by == "rules"
    assert out.origin is None and set(out.unsure) >= {"origin", "destination"}
    assert out.departure_local and out.departure_local.endswith("T07:00")
