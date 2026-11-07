from config.env import get_env
from providers.routing.base import LatLon, RouteCandidate, RoutingProvider
from providers.routing.osrm import OsrmRouting
from providers.routing.tomtom import TomTomRouting

__all__ = ["LatLon", "RouteCandidate", "RoutingProvider", "get_routing_provider"]


def get_routing_provider() -> RoutingProvider:
    """TomTom when a key is configured (truck-aware); otherwise OSRM (car speeds, capped later)."""
    env = get_env()
    if env.routing_provider == "tomtom" or (env.routing_provider != "osrm" and env.tomtom_api_key):
        if not env.tomtom_api_key:
            raise RuntimeError("ROUTING_PROVIDER=tomtom but TOMTOM_API_KEY is empty")
        return TomTomRouting(env.tomtom_api_key.get_secret_value())
    return OsrmRouting()
