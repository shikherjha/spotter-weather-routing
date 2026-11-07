import { describe, expect, it } from "vitest";

import type { Warning } from "../api/types";
import { H, T0, checkpoint, route, trip } from "../test/fixtures";
import { leaveLater, routeStatus, shortArea, troubleSpots, verdict, warningsOn } from "./summary";

describe("verdict", () => {
  it("names the hazard, the town and its local time when the safest route still has bad weather", () => {
    const r = route("B", [0, 0, 0, 0, 0, 0, 3, 0]);
    r.checkpoints[6].place = "Trinidad, CO";
    const v = verdict(trip([r, route("A", [0, 4, 0])]));
    expect(v).toMatchObject({ label: "Drive with caution", headline: "Take Route B" });
    expect(v.sentence).toBe("Heavy snow near Trinidad, CO around Sat 9:00 PM MST, but it's still the safest of the 2.");
  });

  it("doesn't call a route clear past the end of the forecast", () => {
    const r = route("B", [0, 0, 0, null, null], { score: { ...route("x", [0]).score, unknown_mi: 150 } });
    expect(verdict(trip([r], { recommendation: { route_id: "B", advice: "go", headline: "", reasons: [] } })).sentence).toBe(
      "Clear weather as far as the forecast goes, to mile 300.",
    );
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
    const shared = checkpoint(300, 4, { drivers: ["wind"], snow_in_hr: 0 });
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

describe("leave later", () => {
  const option = { offset_h: 11, departure: T0 + 11 * H, route_id: "B", advice: "go" as const, no_travel_mi: 0, severe_mi: 0, high_mi: 0, avg_risk: 0, duration_s: 22 * H, unknown_mi: 0 };

  it("only suggests waiting when the advisor found a better hour", () => {
    expect(leaveLater(trip([route("B", [0, 0])]))).toBeNull();
    const t = trip([route("B", [0, 0, 0, 0, 0, 0])], { departure_advice: { best_offset_h: 11, options: [option] } });
    expect(leaveLater(t)).toMatchObject({ title: "Leave Sat 11:00 PM instead", sub: "Clear all the way · arrive Sun 8:00 PM MST" });
  });

  it("doesn't promise a clear trip the forecast doesn't cover", () => {
    const t = trip([route("B", [0, 0, 0, 0, 0, 0])], { departure_advice: { best_offset_h: 11, options: [{ ...option, unknown_mi: 80 }] } });
    expect(leaveLater(t)?.sub).toMatch(/^Clear as far as the forecast goes/);
  });
});

describe("warnings", () => {
  const warning = (relevant: boolean, routeId = "B"): Warning => ({
    id: relevant ? "w1" : "w2",
    event: relevant ? "Winter Storm Warning" : "Frost Advisory",
    severity: "Severe",
    area: "Raton Pass; Trinidad; Southern Colfax County",
    starts: T0,
    ends: T0 + 20 * H,
    summary: "Heavy snow expected.",
    instruction: "",
    hazard: relevant ? "snow_ice" : "temperature",
    relevant,
    road_closure: relevant,
    truck_risk: relevant ? 0.96 : 0.3,
    triage: "jev",
    source: "simulated",
    url: null,
    routes: [{ route_id: routeId, from_mi: 575, to_mi: 625, enter: T0 + 9 * H, tz: "America/Denver" }],
  });

  it("splits warnings into the ones that matter to a truck and the ones Jev set aside", () => {
    const t = trip([route("B", [0, 0])], { warnings: [warning(true), warning(false), warning(true, "A")] });
    expect(warningsOn(t, "B").map((x) => x.warning.event)).toEqual(["Winter Storm Warning"]);
    expect(warningsOn(t, "B", false).map((x) => x.warning.event)).toEqual(["Frost Advisory"]);
  });

  it("shortens long NWS area lists", () => {
    expect(shortArea("Raton Pass; Trinidad; Southern Colfax County")).toBe("Raton Pass, Trinidad and 1 more");
    expect(shortArea("Logan; Gove")).toBe("Logan and Gove");
  });
});
