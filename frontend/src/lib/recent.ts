// The last few trips planned on this device, for the home screen.
import type { Trip, TripRequest } from "../api/types";
import { cityName } from "./route";
import { longWhen } from "./time";
import { readJson, writeJson } from "./storage";

const KEY = "recent-trips";
const KEEP = 4;

export interface RecentTrip {
  id: string;
  title: string; // "Dallas → Denver"
  detail: string; // "Mon 12:00 PM CST · Route B"
  request: TripRequest; // to plan it again once the saved trip has expired
}

export const recentTrips = (): RecentTrip[] => readJson<RecentTrip[]>(KEY, []);

export function remember(trip: Trip, request: TripRequest, routeId: string): void {
  const entry: RecentTrip = {
    id: trip.id,
    title: `${cityName(trip.origin.label)} → ${cityName(trip.destination.label)}`,
    detail: `${longWhen(trip.departure, trip.origin_tz)} · Route ${routeId}`,
    request,
  };
  const others = recentTrips().filter((r) => r.title !== entry.title);
  writeJson(KEY, [entry, ...others].slice(0, KEEP));
}
