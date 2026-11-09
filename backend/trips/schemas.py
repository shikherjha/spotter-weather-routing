"""API contract. Pydantic models are the single source of truth: they validate input,
generate the OpenAPI schema, and (via codegen) the frontend's TypeScript types."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator, model_validator

from engine.rules import WindBasis
from engine.scoring import Advice
from engine.weather import Confidence


class PlaceIn(BaseModel):
    label: str = Field(max_length=200)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class TripRequest(BaseModel):
    origin: PlaceIn
    destination: PlaceIn
    departure_local: datetime = Field(description="Wall-clock time at the origin; any offset is ignored")
    load_lb: float = Field(ge=0, le=120_000)
    height_ft: float = Field(default=13.5, ge=8, le=16, description="Truck height; routes avoid lower clearances")
    hazmat: bool = Field(default=False, description="Hazardous load; routes avoid roads and tunnels closed to it")
    interval_mi: Literal[10, 25, 50] = 25
    wind_basis: WindBasis = WindBasis.SUSTAINED
    hos: bool = Field(default=True, description="Apply FMCSA Hours-of-Service rest stops to ETAs")
    weather: Literal["live", "demo_storm"] = Field(
        default="live", description="demo_storm swaps the forecast for a labelled, simulated storm"
    )

    @model_validator(mode="after")
    def _distinct_endpoints(self) -> TripRequest:
        if abs(self.origin.lat - self.destination.lat) < 1e-3 and abs(self.origin.lon - self.destination.lon) < 1e-3:
            raise ValueError("origin and destination are the same place")
        return self


class PlaceOut(BaseModel):
    label: str
    lat: float
    lon: float


class StopOut(BaseModel):
    mile: float
    lat: float
    lon: float
    kind: Literal["break", "rest"]
    arrive: int
    depart: int
    tz: str
    place: str | None = Field(default=None, description="The truck stop or rest area it's planned at")
    place_kind: Literal["truck_stop", "rest_area"] | None = None


class RoutePlaceOut(BaseModel):
    kind: Literal["truck_stop", "rest_area"]
    name: str
    mile: float
    lat: float
    lon: float


class WeighStationOut(BaseModel):
    mile: float
    lat: float
    lon: float
    name: str
    eta: int
    tz: str


class CheckpointOut(BaseModel):
    mile: float
    lat: float
    lon: float
    eta: int
    tz: str
    wind_mph: float | None
    gust_mph: float | None
    rain_in_hr: float | None
    snow_in_hr: float | None
    crosswind_mph: float | None
    level: int | None = Field(description="0 Low .. 4 No Travel; null = beyond forecast")
    drivers: list[str]
    reason: str
    load_escalated: bool
    confidence: Confidence
    place: str | None = Field(default=None, description="Nearest named place, from NWS; null if unknown")


class SegmentOut(BaseModel):
    from_mi: float
    to_mi: float
    level: int | None


class ScoreOut(BaseModel):
    miles_by_level: list[float] = Field(description="Indexed by level: Low, Moderate, High, Severe, No Travel")
    unknown_mi: float
    no_travel_mi: float
    severe_mi: float
    high_mi: float
    avg_risk: float


class DecisionOut(BaseModel):
    criterion: str | None
    label: str
    this_value: float | None
    winner_value: float | None


class RouteOut(BaseModel):
    id: str
    rank: int
    recommended: bool
    provider: str
    truck_aware: bool
    distance_mi: float
    drive_s: float
    duration_s: float
    arrival: int
    path: list[tuple[float, float]] = Field(description="[lon, lat] vertices, simplified for display")
    path_mi: list[float] = Field(description="Miles along the route at each path vertex")
    stops: list[StopOut]
    weigh_stations: list[WeighStationOut] = []
    places: list[RoutePlaceOut] = Field(default=[], description="Truck stops and rest areas within a mile of the route")
    checkpoints: list[CheckpointOut]
    segments: list[SegmentOut]
    score: ScoreOut
    lost_on: DecisionOut | None


class RecommendationOut(BaseModel):
    route_id: str
    advice: Advice
    headline: str
    reasons: list[str]


class DepartureOptionOut(BaseModel):
    offset_h: int
    departure: int
    route_id: str
    advice: Advice
    no_travel_mi: float
    severe_mi: float
    high_mi: float
    avg_risk: float
    duration_s: float
    unknown_mi: float


class DepartureAdviceOut(BaseModel):
    best_offset_h: int
    options: list[DepartureOptionOut]


class HeatmapOut(BaseModel):
    """Corridor risk for the 0-48 h slider, byte-packed so moving the slider never touches the network.

    risk: base64 uint8[cells x hours], row-major; 0-4 level, 255 = no data.
    """

    cells: list[str]
    start: int
    hours: int
    risk: str
    resolution: int = Field(description="H3 resolution of `cells`")


Hazard = Literal["snow_ice", "wind", "flood", "visibility", "storm", "temperature", "other"]


class WarningHitOut(BaseModel):
    route_id: str
    from_mi: float
    to_mi: float
    enter: int = Field(description="When the truck first reaches the warned area")
    tz: str


class WarningOut(BaseModel):
    """An official alert the truck would drive into while it is in effect."""

    id: str
    event: str
    severity: str
    area: str
    starts: int
    ends: int | None
    summary: str = Field(description="The alert's own WHAT and IMPACTS lines")
    instruction: str
    hazard: Hazard
    relevant: bool = Field(description="Jev: does this matter to a heavy, high-sided truck?")
    road_closure: bool
    truck_risk: float
    triage: Literal["jev", "rules"]
    source: Literal["nws", "simulated"]
    url: str | None
    routes: list[WarningHitOut]


class TimingsOut(BaseModel):
    routing_ms: int
    weather_ms: int
    compute_ms: int
    total_ms: int


class TripOut(BaseModel):
    id: str
    created: int
    origin: PlaceOut
    destination: PlaceOut
    departure: int
    origin_tz: str
    load_lb: float
    height_ft: float = 13.5
    hazmat: bool = False
    interval_mi: int
    wind_basis: WindBasis
    hos: bool
    forecast_issued: int
    weather_model: str
    weather_points: int
    routes: list[RouteOut]
    recommendation: RecommendationOut
    departure_advice: DepartureAdviceOut
    heatmap: HeatmapOut
    warnings: list[WarningOut] = []
    warnings_status: Literal["ok", "unavailable"] = "ok"
    timings: TimingsOut


class ParseIn(BaseModel):
    text: str = Field(min_length=3, max_length=300)
    tz: str = Field(default="America/Chicago", description="The browser's time zone, used if no origin is found")

    @field_validator("tz")
    @classmethod
    def _known_zone(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError):
            return "America/Chicago"
        return v


class ParsedTripOut(BaseModel):
    """Form fields read from a sentence; null = not found. The driver checks them before planning."""

    origin: PlaceOut | None
    destination: PlaceOut | None
    departure_local: str | None
    load_lb: float | None
    interval_mi: Literal[10, 25, 50] | None
    unsure: list[Literal["origin", "destination", "departure"]]
    read_by: Literal["jev", "rules"]


class PlaceSuggestion(BaseModel):
    label: str
    lat: float
    lon: float


class ErrorOut(BaseModel):
    detail: str
