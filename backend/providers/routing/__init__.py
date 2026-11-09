from collections.abc import Sequence
from datetime import datetime

from config.env import get_env
from providers.http import UpstreamError
from providers.routing.base import LatLon, RouteCandidate, RoutingProvider, Truck
from providers.routing.osrm import OsrmRouting
from providers.routing.tomtom import TomTomRouting
from providers.routing.valhalla import ValhallaRouting

__all__ = ["LatLon", "RouteCandidate", "RoutingProvider", "Truck", "get_routing_provider"]


class WithFallback:
    """Our own Valhalla server first; TomTom if it's down, so a server problem never stops a trip."""

    truck_aware = True

    def __init__(self, primary: RoutingProvider, backup: RoutingProvider) -> None:
        self._primary, self._backup = primary, backup
        self.name = primary.name

    async def routes(
        self, waypoints: Sequence[LatLon], depart_at: datetime, truck: Truck, alternatives: int
    ) -> list[RouteCandidate]:
        try:
            return await self._primary.routes(waypoints, depart_at, truck, alternatives)
        except UpstreamError as e:
            if e.status is not None and 400 <= e.status < 500:
                raise  # the request itself is the problem (e.g. no truck route); TomTom would agree
            return await self._backup.routes(waypoints, depart_at, truck, alternatives)


def get_routing_provider() -> RoutingProvider:
    """ROUTING_PROVIDER picks it: Valhalla (ours, TomTom as backup), TomTom, or OSRM (car speeds, capped later)."""
    env = get_env()
    if env.routing_provider == "osrm":
        return OsrmRouting()
    tomtom = TomTomRouting(env.tomtom_api_key.get_secret_value()) if env.tomtom_api_key else None
    if env.routing_provider == "valhalla":
        if not env.valhalla_url:
            raise RuntimeError("ROUTING_PROVIDER=valhalla but VALHALLA_URL is empty")
        token = env.valhalla_token.get_secret_value() if env.valhalla_token else None
        valhalla = ValhallaRouting(env.valhalla_url, token)
        return WithFallback(valhalla, tomtom) if tomtom else valhalla
    if tomtom is None:
        raise RuntimeError("ROUTING_PROVIDER=tomtom but TOMTOM_API_KEY is empty")
    return tomtom
