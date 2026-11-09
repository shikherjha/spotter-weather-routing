"""Typed application settings, loaded once from the environment / repo-root .env."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class AppEnv(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", env_file_encoding="utf-8", extra="ignore")

    django_secret_key: SecretStr = SecretStr("insecure-dev-key")
    django_debug: bool = False
    django_allowed_hosts: str = "localhost,127.0.0.1"
    redis_url: str | None = None
    cors_allowed_origins: str = "http://localhost:5173"

    routing_provider: Literal["valhalla", "tomtom", "osrm"] = "osrm"
    tomtom_api_key: SecretStr | None = None
    valhalla_url: str | None = None
    valhalla_token: SecretStr | None = None

    open_meteo_api_key: SecretStr | None = None
    weather_model: str = "ncep_nbm_conus"

    typesafe_api_key: SecretStr | None = None
    typesafe_model: str = "jev-1.14.0"

    http_timeout_s: float = Field(default=15.0, gt=0)

    # Data the worker keeps on disk: the NBM forecast copy, NWS zone outlines, truck stops.
    data_dir: Path = REPO_ROOT / "var"

    @property
    def allowed_hosts(self) -> list[str]:
        return [h.strip() for h in self.django_allowed_hosts.split(",") if h.strip()]

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]


@lru_cache
def get_env() -> AppEnv:
    return AppEnv()
