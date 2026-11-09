"""Keep the data trips read locally up to date, so planning a trip never waits on NWS or NOAA.

  * NWS zone outlines: on start, then daily (they change a few times a year)
  * every active NWS alert in the US: every minute
  * the NBM forecast copy: checks every 10 minutes for a newer complete run (hourly)

Each job fails on its own: a NOAA outage leaves the alerts refreshing, and trips fall back to
the network providers for whatever is missing or stale.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from django.core.management.base import BaseCommand

from config.env import get_env
from providers import nws, zones
from providers.weather import nbm

log = logging.getLogger("worker")

ALERTS_EVERY_S = 60
FORECAST_EVERY_S = 10 * 60
ZONES_EVERY_S = 24 * 3600


async def _zones() -> None:
    await zones.ensure(get_env().data_dir / "zones")


async def _alerts() -> None:
    n = await nws.refresh_nationwide()
    log.info("NWS alerts refreshed: %d active", n)


async def _forecast() -> None:
    root = get_env().data_dir
    index = zones.load(root / "zones")
    if index is None:
        log.info("forecast sync waits for the zone outlines")
        return
    await nbm.sync(root / "forecast", index.conus)


async def _every(seconds: float, job: Callable[[], Awaitable[None]]) -> None:
    while True:
        started = time.monotonic()
        try:
            await job()
        except Exception:
            log.exception("%s failed", job.__name__.strip("_"))
        await asyncio.sleep(max(seconds - (time.monotonic() - started), 1.0))


async def _run(once: bool) -> None:
    if once:
        for job in (_zones, _alerts, _forecast):
            await job()
        return
    await _zones()  # the forecast needs the US outline
    await asyncio.gather(
        _every(ZONES_EVERY_S, _zones),
        _every(ALERTS_EVERY_S, _alerts),
        _every(FORECAST_EVERY_S, _forecast),
    )


class Command(BaseCommand):
    help = "Keep NWS zones and alerts and the NOAA NBM forecast copy fresh."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--once", action="store_true", help="run every job once and exit")

    def handle(self, *args: Any, **options: Any) -> None:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
        asyncio.run(_run(bool(options["once"])))
