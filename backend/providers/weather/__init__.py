from collections.abc import Sequence
from typing import Protocol

from config.env import get_env
from engine.weather import WeatherGrid
from providers.weather.local import LocalForecast
from providers.weather.openmeteo import OpenMeteoWeather


class WeatherProvider(Protocol):
    model: str
    point_budget: int  # most cells one trip may ask for
    sample_res: int  # H3 resolution the heatmap's weather is read at

    async def grid(self, cells: Sequence[str]) -> WeatherGrid: ...


MIN_COVERAGE = 0.95  # below this a trip leaves the local copy's area (Alaska, Hawaii, abroad)


def get_weather_provider(points: Sequence[tuple[float, float]] = ()) -> WeatherProvider:
    """The local NBM copy when the worker keeps one fresh and it covers `points` (lat, lon), else Open-Meteo."""
    env = get_env()
    local = LocalForecast.open(env.data_dir / "forecast")
    if local is not None and local.coverage(points) >= MIN_COVERAGE:
        return local
    key = env.open_meteo_api_key.get_secret_value() if env.open_meteo_api_key else None
    return OpenMeteoWeather(env.weather_model, key or None)
