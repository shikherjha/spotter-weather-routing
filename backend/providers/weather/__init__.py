from collections.abc import Sequence
from typing import Protocol

from config.env import get_env
from engine.weather import WeatherGrid


class WeatherProvider(Protocol):
    model: str
    point_budget: int  # most cells one trip may ask for
    sample_res: int  # H3 resolution the heatmap's weather is read at

    async def grid(self, cells: Sequence[str]) -> WeatherGrid: ...


def get_weather_provider() -> WeatherProvider:
    """The local NBM copy when the worker keeps one fresh, else Open-Meteo."""
    from providers.weather.local import LocalForecast
    from providers.weather.openmeteo import OpenMeteoWeather

    env = get_env()
    if (local := LocalForecast.open(env.data_dir / "forecast")) is not None:
        return local
    key = env.open_meteo_api_key.get_secret_value() if env.open_meteo_api_key else None
    return OpenMeteoWeather(env.weather_model, key or None)
