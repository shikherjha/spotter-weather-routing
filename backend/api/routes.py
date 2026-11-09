import logging
from typing import Any

from django.http import HttpRequest, HttpResponse
from ninja import NinjaAPI, Query, Schema, Status
from pydantic import Field

from providers import nws, osm_places
from providers.http import UpstreamError
from providers.places import search_places
from trips import schemas as s
from trips.parse import parse_trip
from trips.service import TripError, get_trip, plan_trip

log = logging.getLogger(__name__)
api = NinjaAPI(title="Weather-Aware Truck Routing", version="0.2.0")


class Health(Schema):
    status: str


class PlacesQuery(Schema):
    q: str = Field(min_length=2, max_length=120)


@api.exception_handler(TripError)
def _trip_error(request: HttpRequest, exc: TripError) -> HttpResponse:
    return api.create_response(request, {"detail": str(exc)}, status=422)


@api.exception_handler(UpstreamError)
def _upstream_error(request: HttpRequest, exc: UpstreamError) -> HttpResponse:
    log.warning("upstream failure: %s", exc)
    status = 503 if exc.status == 429 else 502
    detail = (
        f"{exc.provider} is busy right now; try again in a minute."
        if exc.status == 429
        else f"{exc.provider} is unavailable right now."
    )
    return api.create_response(request, {"detail": detail}, status=status)


@api.get("/health", response=Health)
async def health(request: HttpRequest) -> Health:
    return Health(status="ok")


@api.get("/places", response=list[s.PlaceSuggestion])
async def places(request: HttpRequest, query: Query[PlacesQuery]) -> list[s.PlaceSuggestion]:
    found = await search_places(query.q)
    return [s.PlaceSuggestion(label=p.label, lat=p.lat, lon=p.lon) for p in found]


@api.get("/alerts", response=s.AlertAreasOut)
async def alerts(request: HttpRequest, response: HttpResponse) -> dict[str, Any]:
    """Every active NWS warning, advisory and watch in the US, as GeoJSON for the map."""
    response["Cache-Control"] = "public, max-age=60"
    return await nws.cached_areas() or {"type": "FeatureCollection", "updated": None, "features": []}


@api.get("/pois", response=s.PoisOut)
async def pois(request: HttpRequest, response: HttpResponse) -> dict[str, list[tuple[float, float, str]]]:
    """Truck stops, rest areas and weigh stations across the US (OpenStreetMap), for the map's layers."""
    response["Cache-Control"] = "public, max-age=86400"
    return osm_places.for_map()


@api.post("/parse", response=s.ParsedTripOut)
async def parse(request: HttpRequest, body: s.ParseIn) -> s.ParsedTripOut:
    """Fill the trip form from one typed sentence; the driver confirms before planning."""
    return await parse_trip(body.text, body.tz)


@api.post("/trips", response={200: s.TripOut, 422: s.ErrorOut, 502: s.ErrorOut, 503: s.ErrorOut})
async def create_trip(request: HttpRequest, response: HttpResponse, body: s.TripRequest) -> s.TripOut:
    trip = await plan_trip(body)
    t = trip.timings
    response["Server-Timing"] = (
        f"routing;dur={t.routing_ms}, weather;dur={t.weather_ms}, compute;dur={t.compute_ms}, total;dur={t.total_ms}"
    )
    return trip


@api.get("/trips/{trip_id}", response={200: s.TripOut, 404: s.ErrorOut})
async def read_trip(request: HttpRequest, trip_id: str) -> s.TripOut | Status[dict[str, str]]:
    trip = await get_trip(trip_id)
    if trip is None:
        return Status(404, {"detail": "Trip not found or expired."})
    return trip
