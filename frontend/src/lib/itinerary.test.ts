import { describe, expect, it } from "vitest";

import type { Level } from "../api/types";
import { H, T0, route, trip } from "../test/fixtures";
import { itinerary } from "./itinerary";

describe("stop-by-stop rows", () => {
  it("keeps the ends, stops, weigh stations, clock changes and weather, plus a row about every 100 miles", () => {
    const levels: Level[] = Array.from({ length: 17 }, (_, i) => (i === 12 ? 3 : 0));
    const r = route("B", levels, {}, 50);
    r.stops = [
      { mile: 480, lat: 0, lon: 0, kind: "break", arrive: T0 + 8 * H, depart: T0 + 8.5 * H, tz: "America/Denver", place: "Love's", place_kind: "truck_stop", town: "Dalhart, TX" },
    ];
    r.weigh_stations = [{ mile: 610, lat: 0, lon: 0, name: "Weigh station", eta: T0 + 10 * H, tz: "America/Denver", town: "Trinidad, CO" }];
    const places = itinerary(trip([r], { interval_mi: 50 }), r, false).map((x) => x.place);
    expect(places).toEqual([
      "Dallas, TX",
      "Mile 100",
      "Mile 200",
      "Mile 300",
      "Mile 400",
      "Into Mountain time",
      "30-min break at Love's, Dalhart, TX",
      "Mile 500",
      "Mile 550",
      "Mile 600",
      "Weigh station near Trinidad, CO",
      "Mile 650",
      "Mile 700",
      "Denver, CO",
    ]);
  });

  it("only marks a clock change when the clock actually changes", () => {
    const r = route("B", [0, 0, 0]);
    r.checkpoints.forEach((c, i) => (c.tz = i === 0 ? "America/Chicago" : "America/Menominee"));
    expect(itinerary(trip([r]), r, true).some((x) => x.kind === "zone")).toBe(false);
  });

  it("shows the day a rest ends when it ends on another day", () => {
    const r = route("B", [0, 0, 0]);
    r.stops = [{ mile: 100, lat: 0, lon: 0, kind: "rest", arrive: T0 + 10 * H, depart: T0 + 20 * H, tz: "America/Chicago", place: null, place_kind: null, town: null }];
    expect(itinerary(trip([r]), r, false).find((x) => x.kind === "stop")?.time).toBe("Sat 10:00 PM CST → Sun 8:00 AM CST");
  });

  it("marks where a warning starts, before the checkpoint at the same mile", () => {
    const r = route("B", [0, 0, 0, 0, 0, 0, 3, 0]);
    r.checkpoints[6].place = "Trinidad, CO";
    const t = trip([r], {
      warnings: [
        {
          id: "w",
          event: "Winter Storm Warning",
          severity: "Severe",
          area: "Raton Pass",
          starts: T0,
          ends: null,
          summary: "",
          instruction: "",
          hazard: "snow_ice",
          relevant: true,
          road_closure: false,
          truck_risk: 0.9,
          triage: "jev",
          source: "nws",
          url: null,
          routes: [{ route_id: "B", from_mi: 600, to_mi: 650, enter: T0 + 10 * H, tz: "America/Denver" }],
        },
      ],
    });
    const rows = itinerary(t, r, false).map((x) => x.place);
    expect(rows.slice(rows.indexOf("Into Winter Storm Warning"), rows.indexOf("Into Winter Storm Warning") + 2)).toEqual([
      "Into Winter Storm Warning",
      "Trinidad, CO",
    ]);
  });
});
