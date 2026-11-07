// Where things are along a route: positions by mile and by time, and lookups on the trip.
import type { Checkpoint, Route, Trip } from "../api/types";
import { HOUR } from "./time";

export const arrivalTz = (r: Route) => r.checkpoints.at(-1)?.tz ?? "UTC";

/** The route with this id, or the recommended one. */
export function routeById(trip: Trip, id: string | null): Route {
  const rec = trip.routes.find((r) => r.recommended) ?? trip.routes[0];
  return trip.routes.find((r) => r.id === id) ?? rec;
}

/** "Dallas, Texas, United States" → "Dallas" */
export const cityName = (label: string) => label.split(",")[0].trim();

/** "Dallas, Texas, United States" → "Dallas, Texas" */
export const placeLabel = (label: string) => label.replace(/, (United States|US|USA)( of America)?$/, "");

/** Worst checkpoint on a route (earliest if tied); null when every forecast checkpoint is Low. */
export function worstCheckpoint(r: Route): Checkpoint | null {
  let worst: Checkpoint | null = null;
  for (const cp of r.checkpoints) if (cp.level && (!worst || cp.level > (worst.level ?? 0))) worst = cp;
  return worst;
}

/** The first checkpoint past the end of the forecast, if the trip runs beyond it. */
export const firstUnforecast = (r: Route): Checkpoint | null => r.checkpoints.find((cp) => cp.level === null) ?? null;

/** Miles along the route at time t, holding still during breaks and rests. */
export function mileAt(r: Route, t: number): number {
  const pts = [
    ...r.checkpoints.map((c) => [c.eta, c.mile] as const),
    ...r.stops.flatMap((s) => [[s.arrive, s.mile] as const, [s.depart, s.mile] as const]),
  ].sort((a, b) => a[0] - b[0]);
  if (t <= pts[0][0]) return pts[0][1];
  for (let i = 1; i < pts.length; i++) {
    const [t1, m1] = pts[i];
    if (t <= t1) {
      const [t0, m0] = pts[i - 1];
      return t1 === t0 ? m1 : m0 + ((m1 - m0) * (t - t0)) / (t1 - t0);
    }
  }
  return pts[pts.length - 1][1];
}

/** [lon, lat] at a mile mark, interpolated along the display path. */
export function pointAtMile(r: Route, mile: number): [number, number] {
  const pm = r.path_mi;
  let i = 1;
  while (i < pm.length - 1 && pm[i] < mile) i++;
  const f = pm[i] === pm[i - 1] ? 0 : Math.min(1, Math.max(0, (mile - pm[i - 1]) / (pm[i] - pm[i - 1])));
  const [a, b] = [r.path[i - 1], r.path[i]];
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f];
}

/** The part of a route's path between two mile marks. */
export function slicePath(r: Route, from: number, to: number): [number, number][] {
  const inner = r.path.filter((_, i) => r.path_mi[i] > from && r.path_mi[i] < to);
  return [pointAtMile(r, from), ...inner, pointAtMile(r, to)];
}

/** The slider's hours (from the heatmap start) during which the truck is on the road. */
export function tripHours(trip: Trip, r: Route): [number, number] {
  const s = trip.heatmap.start;
  return [(trip.departure - s) / HOUR, (r.arrival - s) / HOUR];
}

/** Approximate distance in km; fine for "are these two pins the same place". */
export function km(a: { lat: number; lon: number }, b: { lat: number; lon: number }): number {
  const rad = Math.PI / 180;
  const dLat = (b.lat - a.lat) * rad;
  const dLon = (b.lon - a.lon) * rad * Math.cos(a.lat * rad);
  return 6371 * Math.hypot(dLat, dLon);
}
