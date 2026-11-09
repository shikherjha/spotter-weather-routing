// Small, readable trips for unit tests: one checkpoint per `step` miles at 60 mph.
import type { Checkpoint, Level, Route, Trip } from "../api/types";

export const H = 3600;
export const T0 = Date.UTC(2026, 10, 7, 18) / 1000; // Sat Nov 7 2026, 12:00 PM CST

export function checkpoint(mile: number, level: Level | null, extra: Partial<Checkpoint> = {}): Checkpoint {
  return {
    mile,
    lat: 33 + mile / 100,
    lon: -97 - mile / 100,
    eta: T0 + mile * 60,
    tz: mile < 450 ? "America/Chicago" : "America/Denver",
    wind_mph: 10,
    gust_mph: 14,
    rain_in_hr: 0,
    snow_in_hr: level ? 2.2 : 0,
    crosswind_mph: 5,
    level,
    drivers: level ? ["snow"] : [],
    reason: level ? "snow" : "Within safe limits",
    load_escalated: false,
    confidence: "high",
    place: null,
    ...extra,
  };
}

export function route(id: string, levels: (Level | null)[], extra: Partial<Route> = {}, step = 100): Route {
  const checkpoints = levels.map((l, i) => checkpoint(i * step, l));
  const last = checkpoints[checkpoints.length - 1];
  return {
    id,
    rank: 1,
    recommended: false,
    provider: "test",
    truck_aware: true,
    distance_mi: last.mile,
    drive_s: last.mile * 60,
    duration_s: last.mile * 60,
    arrival: last.eta,
    path: checkpoints.map((c) => [c.lon, c.lat]),
    path_mi: checkpoints.map((c) => c.mile),
    stops: [],
    weigh_stations: [],
    places: [],
    checkpoints,
    segments: [],
    score: { miles_by_level: [0, 0, 0, 0, 0], unknown_mi: 0, no_travel_mi: 0, severe_mi: 0, high_mi: 0, avg_risk: 0 },
    lost_on: null,
    ...extra,
  };
}

/** The first route is the recommended one. */
export function trip(routes: Route[], extra: Partial<Trip> = {}): Trip {
  routes[0].recommended = true;
  return {
    id: "t",
    created: T0,
    origin: { label: "Dallas, TX", lat: 33, lon: -97 },
    destination: { label: "Denver, CO", lat: 39.7, lon: -105 },
    departure: T0,
    origin_tz: "America/Chicago",
    load_lb: 42000,
    height_ft: 13.5,
    hazmat: false,
    interval_mi: 25,
    hos: true,
    forecast_issued: T0,
    weather_model: "test",
    weather_points: 1,
    routes,
    recommendation: { route_id: routes[0].id, advice: "caution", headline: "", reasons: [] },
    departure_advice: { best_offset_h: 0, options: [] },
    heatmap: { cells: [], start: T0, hours: 49, risk: "", resolution: 6 },
    warnings: [],
    warnings_status: "ok",
    ...extra,
  };
}
