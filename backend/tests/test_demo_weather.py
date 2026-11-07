import asyncio

import h3

from providers.weather.demo import DemoStormWeather

RATON = h3.latlng_to_cell(37.0, -104.5, 5)
DALLAS = h3.latlng_to_cell(32.78, -96.8, 5)
NOW = 1_800_000_000.0


def test_demo_storm_snows_on_raton_pass_hours_after_the_next_hour() -> None:
    demo = DemoStormWeather(NOW)
    grid = asyncio.run(demo.grid([RATON, DALLAS]))

    def at(h: float) -> int:
        return int((demo.anchor_s + h * 3600 - grid.times[0]) // 3600)

    assert grid.snow_in_hr[0, at(14)] > 2.0  # mid-storm over the pass
    assert grid.snow_in_hr[0, at(0)] == 0.0  # nothing when the demo trip leaves
    assert grid.snow_in_hr[1].max() < 0.01  # Dallas stays clear of snow


def test_demo_storm_is_fixed_in_time_not_moved_by_departure() -> None:
    a = asyncio.run(DemoStormWeather(NOW).grid([RATON]))
    b = asyncio.run(DemoStormWeather(NOW + 600).grid([RATON]))  # same hour, later call
    assert (a.times == b.times).all() and (a.snow_in_hr == b.snow_in_hr).all()
