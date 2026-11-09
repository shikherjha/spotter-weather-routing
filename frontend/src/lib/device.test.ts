import { beforeEach, describe, expect, it, vi } from "vitest";

import type { TripRequest } from "../api/types";
import { T0, route, trip } from "../test/fixtures";
import { recentTrips, remember, replanRequest } from "./recent";
import { DEFAULT_TRUCK, saveTruck, savedTruck } from "./truck";

function memoryStorage(): Storage {
  const data = new Map<string, string>();
  return {
    get length() {
      return data.size;
    },
    clear: () => data.clear(),
    getItem: (k) => data.get(k) ?? null,
    key: (i) => [...data.keys()][i] ?? null,
    removeItem: (k) => void data.delete(k),
    setItem: (k, v) => void data.set(k, String(v)),
  };
}

const request = (city: string): TripRequest => ({
  origin: { label: "Dallas, TX", lat: 32.8, lon: -96.8 },
  destination: { label: `${city}, CO`, lat: 39.7, lon: -105 },
  departure_local: "2026-11-07T12:00",
  load_lb: 30000,
  height_ft: 13.5,
  hazmat: false,
  interval_mi: 25,
  hos: true,
  weather: "live",
});

beforeEach(() => {
  vi.stubGlobal("localStorage", memoryStorage());
});

describe("recent trips", () => {
  it("keeps the latest four, one per city pair, newest first", () => {
    for (const city of ["Denver", "Pueblo", "Aspen", "Vail", "Denver"]) {
      const t = trip([route("B", [0, 0])], { id: city, destination: { label: `${city}, CO`, lat: 39, lon: -105 } });
      remember(t, request(city), "B");
    }
    expect(recentTrips().map((r) => r.id)).toEqual(["Denver", "Vail", "Aspen", "Pueblo"]);
  });

  it("doesn't keep the simulated-storm demo", () => {
    remember(trip([route("B", [0, 0])]), { ...request("Denver"), weather: "demo_storm" }, "B");
    expect(recentTrips()).toEqual([]);
  });

  it("ignores whatever else is stored under its key", () => {
    localStorage.setItem("corridor:recent-trips", JSON.stringify({ not: "a list" }));
    expect(recentTrips()).toEqual([]);
    localStorage.setItem("corridor:recent-trips", JSON.stringify([null, { id: 1 }]));
    expect(recentTrips()).toEqual([]);
  });

  it("re-plans an expired trip to leave on the next hour, in the origin's time zone", () => {
    remember(trip([route("B", [0, 0])]), request("Denver"), "B");
    const [r] = recentTrips();
    const later = new Date((T0 + 3 * 86400) * 1000); // Tue Nov 10, 12:00 PM CST
    expect(replanRequest(r, later).departure_local).toBe("2026-11-10T13:00");
    const before = new Date((T0 - 86400) * 1000);
    expect(replanRequest(r, before).departure_local).toBe("2026-11-07T12:00");
  });
});

describe("saved truck", () => {
  it("round-trips, and falls back field by field on anything out of range", () => {
    expect(savedTruck()).toEqual(DEFAULT_TRUCK);
    saveTruck({ load_lb: 42000, height_ft: 14, hazmat: true });
    expect(savedTruck()).toEqual({ load_lb: 42000, height_ft: 14, hazmat: true });
    localStorage.setItem("corridor:my-truck", JSON.stringify({ load_lb: 900000, height_ft: 13.7, hazmat: "yes" }));
    expect(savedTruck()).toEqual(DEFAULT_TRUCK);
  });
});
