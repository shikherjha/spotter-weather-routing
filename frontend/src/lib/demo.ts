// The simulated-storm walkthrough: Dallas → Denver, leaving on the next hour Dallas time.
import { DEMO_WEATHER, type TripRequest } from "../api/types";
import { nextHourInput } from "./time";
import type { SavedTruck } from "./truck";

export const DEMO_ROUTE: Pick<TripRequest, "origin" | "destination" | "load_lb"> = {
  origin: { label: "Dallas, Texas, United States", lat: 32.7767, lon: -96.797 },
  destination: { label: "Denver, Colorado, United States", lat: 39.7392, lon: -104.9903 },
  load_lb: 42000,
};

/** The storm is timed from the next whole hour, so the demo always leaves then. */
export const demoRequest = (truck: Pick<SavedTruck, "height_ft" | "hazmat">): TripRequest => ({
  ...DEMO_ROUTE,
  departure_local: nextHourInput("America/Chicago"),
  height_ft: truck.height_ft,
  hazmat: truck.hazmat,
  interval_mi: 25,
  hos: true,
  weather: DEMO_WEATHER,
});
