import asyncio
import time

import h3

from providers.weather.demo import DemoStormWeather

RATON = h3.latlng_to_cell(37.0, -104.5, 5)
DALLAS = h3.latlng_to_cell(32.78, -96.8, 5)


def test_demo_storm_snows_on_raton_pass_hours_after_departure() -> None:
    dep = time.time() // 3600 * 3600 + 3600
    grid = asyncio.run(DemoStormWeather(dep).grid([RATON, DALLAS]))
    at = lambda h: int(((dep + h * 3600) - grid.times[0]) // 3600)  # noqa: E731
    assert grid.snow_in_hr[0, at(14)] > 2.0  # mid-storm over the pass
    assert grid.snow_in_hr[0, at(0)] == 0.0  # nothing at departure
    assert grid.snow_in_hr[1].max() < 0.01  # Dallas stays clear of snow
