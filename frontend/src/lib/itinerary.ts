// Rows for the stop-by-stop table.
import type { Level, Route, Trip } from "../api/types";
import { levelReason, mainReading } from "./risk";
import { placeLabel } from "./route";
import { warningsOn } from "./summary";
import { sameDay, when, zone, zoneName } from "./time";

export interface Row {
  key: string;
  mile: number;
  place: string;
  time: string;
  weather: string;
  level: Level | null;
  reason: string;
  kind: "zone" | "warning" | "stop" | "point" | "end";
}

// At the same mile, a clock change or a warning boundary reads before the checkpoint it applies to.
const ORDER: Record<Row["kind"], number> = { zone: 0, warning: 1, stop: 2, point: 3, end: 3 };
const LANDMARK_EVERY_MI = 100; // compact mode still shows a checkpoint about this often

/** Compact mode keeps the ends, stops, clock changes, warnings, any weather above Low, and a row every ~100 mi. */
export function itinerary(trip: Trip, r: Route, all: boolean): Row[] {
  const rows: Row[] = [];
  const cps = r.checkpoints;
  const landmarkEvery = Math.max(1, Math.round(LANDMARK_EVERY_MI / trip.interval_mi));
  cps.forEach((cp, i) => {
    const prev = cps[i - 1];
    if (prev && zone(prev.eta, prev.tz) !== zone(cp.eta, cp.tz)) {
      rows.push({
        key: `z${i}`,
        mile: (prev.mile + cp.mile) / 2,
        place: `Into ${zoneName(cp.eta, cp.tz)}`,
        time: "Clocks change here",
        weather: "",
        level: null,
        reason: "",
        kind: "zone",
      });
    }
    const end = i === 0 || i === cps.length - 1;
    const weatherNearby = [cps[i - 1], cp, cps[i + 1]].some((c) => (c?.level ?? 0) > 0);
    if (!all && !end && !weatherNearby && i % landmarkEvery !== 0) return;
    const name = i === 0 ? placeLabel(trip.origin.label) : end ? placeLabel(trip.destination.label) : cp.place;
    rows.push({
      key: `c${i}`,
      mile: cp.mile,
      place: name ?? `Mile ${Math.round(cp.mile)}`,
      time: when(cp.eta, cp.tz),
      weather: mainReading(cp),
      level: cp.level,
      reason: levelReason(cp),
      kind: end ? "end" : "point",
    });
  });
  for (const s of r.stops) {
    rows.push({
      key: `s${s.mile}`,
      mile: s.mile,
      place: s.kind === "break" ? "30-min break" : "10-h rest",
      time: `${when(s.arrive, s.tz)} → ${when(s.depart, s.tz, { day: !sameDay(s.arrive, s.depart, s.tz) })}`,
      weather: "",
      level: null,
      reason: s.kind === "break" ? "Required after 8 h driving" : "Required after 11 h driving",
      kind: "stop",
    });
  }
  for (const { warning, hit } of warningsOn(trip, r.id)) {
    rows.push({
      key: `w${warning.id}`,
      mile: hit.from_mi,
      place: `Into ${warning.event}`,
      time: when(hit.enter, hit.tz),
      weather: "",
      level: null,
      reason: "Official warning",
      kind: "warning",
    });
  }
  return rows.sort((a, b) => a.mile - b.mile || ORDER[a.kind] - ORDER[b.kind]);
}
