// The last few trips planned on this device, for the home screen.
import type { Trip, TripRequest } from "../api/types";
import { cityName } from "./route";
import { readJson, writeJson } from "./storage";
import { longWhen, nextHourInput } from "./time";

const KEY = "recent-trips";
const KEEP = 4;

export interface RecentTrip {
  id: string;
  title: string; // "Dallas → Denver"
  detail: string; // "Mon 12:00 PM CST · Route B"
  tz: string; // the origin's time zone
  request: TripRequest; // to plan it again once the saved trip has expired
}

const isRecent = (r: unknown): r is RecentTrip => {
  const x = r as Partial<RecentTrip> | null;
  return !!x && typeof x.id === "string" && typeof x.title === "string" && typeof x.tz === "string" && !!x.request?.origin;
};

export function recentTrips(): RecentTrip[] {
  const stored = readJson(KEY);
  return Array.isArray(stored) ? stored.filter(isRecent).slice(0, KEEP) : [];
}

/** Remember a planned trip (the simulated-storm demo is always one tap away, so it isn't kept). */
export function remember(trip: Trip, request: TripRequest, routeId: string): void {
  if (request.weather !== "live") return;
  const entry: RecentTrip = {
    id: trip.id,
    title: `${cityName(trip.origin.label)} → ${cityName(trip.destination.label)}`,
    detail: `${longWhen(trip.departure, trip.origin_tz)} · Route ${routeId}`,
    tz: trip.origin_tz,
    request,
  };
  const others = recentTrips().filter((r) => r.title !== entry.title);
  writeJson(KEY, [entry, ...others].slice(0, KEEP));
}

/** A recent trip's request, leaving on the next hour if its departure has passed. */
export function replanRequest(r: RecentTrip, now: Date = new Date()): TripRequest {
  const next = nextHourInput(r.tz, now);
  return r.request.departure_local < next ? { ...r.request, departure_local: next } : r.request;
}
