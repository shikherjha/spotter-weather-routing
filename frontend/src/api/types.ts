// Mirrors backend/trips/schemas.py (the API contract). Keep the two in step.

export type Level = 0 | 1 | 2 | 3 | 4; // Low, Moderate, High, Severe, No Travel
export type Advice = "go" | "caution" | "delay";

export interface Place {
  label: string;
  lat: number;
  lon: number;
}

export interface TripRequest {
  origin: Place;
  destination: Place;
  departure_local: string; // wall-clock at the origin, "YYYY-MM-DDTHH:mm"
  load_lb: number;
  interval_mi: 10 | 25 | 50;
  hos: boolean;
  weather: "live" | "demo_storm";
}

export interface Stop {
  mile: number;
  lat: number;
  lon: number;
  kind: "break" | "rest";
  arrive: number;
  depart: number;
  tz: string;
}

export interface Checkpoint {
  mile: number;
  lat: number;
  lon: number;
  eta: number;
  tz: string;
  wind_mph: number | null;
  gust_mph: number | null;
  rain_in_hr: number | null;
  snow_in_hr: number | null;
  crosswind_mph: number | null;
  level: Level | null; // null = beyond the forecast
  drivers: ("wind" | "rain" | "snow")[];
  reason: string;
  load_escalated: boolean;
  confidence: "high" | "medium" | "low";
  place: string | null; // nearest town, from the NWS
}

export interface Segment {
  from_mi: number;
  to_mi: number;
  level: Level | null;
}

export interface Score {
  miles_by_level: number[];
  unknown_mi: number;
  no_travel_mi: number;
  severe_mi: number;
  high_mi: number;
  avg_risk: number;
}

export interface Route {
  id: string;
  rank: number;
  recommended: boolean;
  provider: string;
  truck_aware: boolean;
  distance_mi: number;
  drive_s: number;
  duration_s: number;
  arrival: number;
  path: [number, number][]; // [lon, lat]
  path_mi: number[];
  stops: Stop[];
  checkpoints: Checkpoint[];
  segments: Segment[];
  score: Score;
  lost_on: { criterion: string | null; label: string; this_value: number | null; winner_value: number | null } | null;
}

export interface DepartureOption {
  offset_h: number;
  departure: number;
  route_id: string;
  advice: Advice;
  no_travel_mi: number;
  severe_mi: number;
  high_mi: number;
  avg_risk: number;
  duration_s: number;
  unknown_mi: number;
}

export interface Heatmap {
  cells: string[];
  start: number;
  hours: number;
  risk: string; // base64 uint8[cells x hours]; 0-4, 255 = no data
  samples: number;
  sample_of: number[];
  sample_wind: string;
  sample_rain: string;
  sample_snow: string;
}

export interface WarningHit {
  route_id: string;
  from_mi: number;
  to_mi: number;
  enter: number;
  tz: string;
}

/** An official NWS alert the truck would drive into while it is in effect. */
export interface Warning {
  id: string;
  event: string;
  severity: string;
  area: string;
  starts: number;
  ends: number | null;
  summary: string; // the alert's own WHAT and IMPACTS lines
  instruction: string;
  hazard: "snow_ice" | "wind" | "flood" | "visibility" | "storm" | "temperature" | "other";
  relevant: boolean; // Jev: does it matter to a heavy, high-sided truck?
  road_closure: boolean;
  truck_risk: number;
  triage: "jev" | "rules";
  source: "nws" | "simulated";
  url: string | null;
  routes: WarningHit[];
}

export interface Trip {
  id: string;
  created: number;
  origin: Place;
  destination: Place;
  departure: number;
  origin_tz: string;
  load_lb: number;
  interval_mi: 10 | 25 | 50;
  hos: boolean;
  forecast_issued: number;
  weather_model: string;
  weather_points: number;
  routes: Route[];
  recommendation: { route_id: string; advice: Advice; headline: string; reasons: string[] };
  departure_advice: { best_offset_h: number; options: DepartureOption[] };
  heatmap: Heatmap;
  warnings: Warning[];
  warnings_status: "ok" | "unavailable";
}
