import { describe, expect, it } from "vitest";

import type { Checkpoint, Level, Route, Trip } from "../api/types";
import { why } from "./risk";
import { duration, when } from "./time";
import { itinerary, leaveLater, mileAt, routeStatus, troubleSpots, verdict } from "./trip";

const T0 = Date.UTC(2026, 10, 7, 18) / 1000; // Sat Nov 7, 12:00 PM CST
const H = 3600;

function cp(mile: number, level: Level, extra: Partial<Checkpoint> = {}): Checkpoint {
  return {
    mile,
    lat: 33 + mile / 100,
    lon: -97 - mile / 100,
    eta: T0 + mile * 60, // 60 mph
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
    ...extra,
  };
}

function route(id: string, levels: Level[], extra: Partial<Route> = {}, step = 100): Route {
  const checkpoints = levels.map((l, i) => cp(i * step, l));
  const last = checkpoints.at(-1)!;
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
    checkpoints,
    segments: [],
    score: { miles_by_level: [0, 0, 0, 0, 0], unknown_mi: 0, no_travel_mi: 0, severe_mi: 0, high_mi: 0, avg_risk: 0 },
    lost_on: null,
    ...extra,
  };
}

function trip(routes: Route[], extra: Partial<Trip> = {}): Trip {
  routes[0].recommended = true;
  return {
    id: "t",
    created: T0,
    origin: { label: "Dallas, TX", lat: 33, lon: -97 },
    destination: { label: "Denver, CO", lat: 39.7, lon: -105 },
    departure: T0,
    origin_tz: "America/Chicago",
    load_lb: 42000,
    interval_mi: 25,
    hos: true,
    forecast_issued: T0,
    weather_model: "test",
    weather_points: 1,
    routes,
    recommendation: { route_id: routes[0].id, advice: "caution", headline: "", reasons: [] },
    departure_advice: { best_offset_h: 0, options: [] },
    heatmap: { cells: [], start: T0, hours: 49, risk: "", samples: 0, sample_of: [], sample_wind: "", sample_rain: "", sample_snow: "" },
    ...extra,
  };
}

describe("time", () => {
  it("names the zone of the place, not the viewer", () => {
    expect(when(T0, "America/Chicago")).toBe("Sat 12:00 PM CST");
    expect(when(T0, "America/Denver")).toBe("Sat 11:00 AM MST");
  });
  it("formats drive time as hours and minutes", () => {
    expect(duration(82_440)).toBe("22 h 54 m");
    expect(duration(1_800)).toBe("30 m");
  });
});

describe("verdict", () => {
  it("names the hazard and its local time when the safest route still has bad weather", () => {
    const t = trip([route("B", [0, 0, 0, 0, 0, 0, 3, 0]), route("A", [0, 4, 0])]);
    expect(verdict(t)).toMatchObject({ label: "Drive with caution", headline: "Take Route B" });
    expect(verdict(t).sentence).toBe("Heavy snow around Sat 9:00 PM MST, but it's still the safest of the 2.");
  });
});

describe("route status", () => {
  it("calls the pick safest and names what is wrong with the others", () => {
    const t = trip([route("B", [0, 0]), route("A", [0, 4], { duration_s: 1 })]);
    expect(routeStatus(t, t.routes[0])).toEqual({ text: "Safest", tone: "good" });
    expect(routeStatus(t, t.routes[1])).toEqual({ text: "Extreme snow", tone: "bad" });
  });
  it("says how much slower a clear alternative is", () => {
    const t = trip([route("B", [0, 0]), route("C", [0, 0], { duration_s: 100 * 60 + 33 * 60 })]);
    expect(routeStatus(t, t.routes[1]).text).toBe("33 m slower");
  });
});

describe("trouble spots", () => {
  it("makes one pin per bad stretch and merges stretches that routes share", () => {
    const shared = cp(300, 4, { drivers: ["wind"], snow_in_hr: 0 });
    const a = route("A", [0, 0, 0, 0]);
    const c = route("C", [0, 0, 0, 0]);
    a.checkpoints[3] = { ...shared };
    c.checkpoints[3] = { ...shared, eta: shared.eta + H };
    const pins = troubleSpots(trip([route("B", [0, 2, 2, 0]), a, c]));
    expect(pins.map((p) => [p.title, p.detail])).toEqual([
      ["Snow", "1:40 PM"],
      ["Unsafe wind", "Routes A, C"],
    ]);
  });
});

describe("position on the route", () => {
  it("holds still during a rest stop", () => {
    const r = route("B", [0, 0, 0, 0]);
    r.stops = [{ mile: 150, lat: 0, lon: 0, kind: "rest", arrive: T0 + 150 * 60, depart: T0 + 150 * 60 + 10 * H, tz: "America/Chicago" }];
    r.checkpoints = r.checkpoints.map((c) => (c.mile > 150 ? { ...c, eta: c.eta + 10 * H } : c));
    expect(mileAt(r, T0 + 150 * 60 + 5 * H)).toBe(150);
    expect(mileAt(r, T0 - H)).toBe(0);
  });
});

describe("stop-by-stop rows", () => {
  it("keeps the ends, stops, zone changes and weather, and drops calm miles", () => {
    const levels: Level[] = Array.from({ length: 17 }, (_, i) => (i === 12 ? 3 : 0));
    const r = route("B", levels, {}, 50);
    r.stops = [{ mile: 480, lat: 0, lon: 0, kind: "break", arrive: T0 + 8 * H, depart: T0 + 8.5 * H, tz: "America/Denver" }];
    const places = itinerary(trip([r]), r, false).map((x) => x.place);
    expect(places).toEqual([
      "Dallas, TX",
      "Mile 100",
      "Mile 200",
      "Mile 300",
      "Mile 400",
      "Into Mountain time",
      "30-min break",
      "Mile 500",
      "Mile 550",
      "Mile 600",
      "Mile 650",
      "Mile 700",
      "Denver, CO",
    ]);
  });
});

describe("leave later", () => {
  it("only suggests waiting when the advisor found a better hour", () => {
    expect(leaveLater(trip([route("B", [0, 0])]))).toBeNull();
    const t = trip([route("B", [0, 0, 0, 0, 0, 0])], {
      departure_advice: {
        best_offset_h: 11,
        options: [
          { offset_h: 11, departure: T0 + 11 * H, route_id: "B", advice: "go", no_travel_mi: 0, severe_mi: 0, high_mi: 0, avg_risk: 0, duration_s: 22 * H, unknown_mi: 0 },
        ],
      },
    });
    expect(leaveLater(t)).toMatchObject({ title: "Leave Sat 11:00 PM instead", sub: "Clear all the way · arrive Sun 8:00 PM MST" });
  });
});

describe("why", () => {
  it("explains a load-rule escalation in words", () => {
    expect(why(cp(0, 4, { drivers: ["wind"], load_escalated: true }))).toBe("Wind 45–54 mph, load over 30,000 lb");
    expect(why(cp(0, 3))).toBe("Snow 2–3 in/hr");
  });
});
