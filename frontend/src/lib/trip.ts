// Turns the API's numbers into the few plain sentences and markers the screen shows.
import type { Checkpoint, Level, Route, Trip, Warning, WarningHit } from "../api/types";
import { hazard, isBad, LEVEL_NAMES, reading, why } from "./risk";
import { clock, when, zoneName } from "./time";

const HOUR = 3600;

export const arrivalTz = (r: Route) => r.checkpoints.at(-1)?.tz ?? "UTC";
export const routeById = (trip: Trip, id: string) => trip.routes.find((r) => r.id === id) ?? trip.routes[0];

/** Worst checkpoint on a route (earliest if tied); null when the whole route is Low. */
export function worst(r: Route): Checkpoint | null {
  let best: Checkpoint | null = null;
  for (const cp of r.checkpoints) if (cp.level && (!best || cp.level > (best.level ?? 0))) best = cp;
  return best;
}

export type Tone = "good" | "bad" | "plain";

/** One or two words per route for the route list: "Safest", "Unsafe wind", "+33 m". */
export function routeStatus(trip: Trip, r: Route): { text: string; tone: Tone } {
  if (r.recommended) return { text: trip.routes.length > 1 ? "Safest" : "Only route", tone: "good" };
  const w = worst(r);
  if (w && isBad(w.level)) return { text: hazard(w), tone: (w.level ?? 0) >= 3 ? "bad" : "plain" };
  const rec = trip.routes.find((x) => x.recommended)!;
  const extra = Math.round((r.duration_s - rec.duration_s) / 60);
  return { text: extra > 0 ? `${extra >= 60 ? `${Math.floor(extra / 60)} h ` : ""}${extra % 60} m slower` : "Also clear", tone: "plain" };
}

export function verdict(trip: Trip) {
  const rec = routeById(trip, trip.recommendation.route_id);
  const w = worst(rec);
  const advice = trip.recommendation.advice;
  const label = advice === "go" ? "Good to go" : advice === "caution" ? "Drive with caution" : "Wait if you can";
  const n = trip.routes.length;
  let sentence: string;
  if (advice === "delay") {
    sentence = `Every route crosses No Travel weather. Route ${rec.id} has the least of it.`;
  } else if (!w || !isBad(w.level)) {
    sentence = n > 1 ? `Clear weather the whole way, and the fastest safe option of ${n}.` : "Clear weather the whole way.";
  } else {
    const at = `${hazard(w)}${w.place ? ` near ${w.place}` : ""} around ${when(w.eta, w.tz)}`;
    sentence =
      advice === "caution"
        ? `${at}, but ${n > 1 ? `it's still the safest of the ${n}` : "it's the only route found"}.`
        : `${at}; nothing worse than High on the way.`;
  }
  return { label, headline: `Take Route ${rec.id}`, sentence, advice };
}

/** The departure advisor's suggestion, if waiting is actually safer. */
export function leaveLater(trip: Trip) {
  const { best_offset_h: h, options } = trip.departure_advice;
  if (h <= 0) return null;
  const opt = options.find((o) => o.offset_h === h);
  if (!opt) return null;
  const route = routeById(trip, opt.route_id);
  const clear = opt.no_travel_mi === 0 && opt.severe_mi === 0 && opt.high_mi === 0;
  return {
    offsetH: h,
    departure: opt.departure,
    title: `Leave ${when(opt.departure, trip.origin_tz, { zone: false })} instead`,
    sub: `${clear ? "Clear all the way" : "Less bad weather"} · arrive ${when(opt.departure + opt.duration_s, arrivalTz(route))}`,
  };
}

export interface Pin {
  key: string;
  lat: number;
  lon: number;
  level: Level;
  title: string; // "Heavy snow"
  detail: string; // "9:10 PM" or "Routes A, C"
  routeIds: string[];
  cp: Checkpoint;
  routeId: string;
}

const km = (a: { lat: number; lon: number }, b: { lat: number; lon: number }) => {
  const dLat = ((b.lat - a.lat) * Math.PI) / 180;
  const dLon = ((b.lon - a.lon) * Math.PI) / 180 * Math.cos((a.lat * Math.PI) / 180);
  return 6371 * Math.hypot(dLat, dLon);
};

/** One pin per stretch of High-or-worse weather; stretches shared by several routes merge into one pin. */
export function troubleSpots(trip: Trip, max = 4): Pin[] {
  const peaks: { cp: Checkpoint; routeId: string }[] = [];
  for (const r of trip.routes) {
    let run: Checkpoint | null = null;
    for (const cp of [...r.checkpoints, null]) {
      if (cp && isBad(cp.level)) {
        if (!run || (cp.level ?? 0) > (run.level ?? 0)) run = cp;
      } else if (run) {
        peaks.push({ cp: run, routeId: r.id });
        run = null;
      }
    }
  }
  const pins: Pin[] = [];
  for (const p of peaks.sort((a, b) => (b.cp.level ?? 0) - (a.cp.level ?? 0))) {
    const near = pins.find((q) => km(q, p.cp) < 60 && hazard(q.cp) === hazard(p.cp));
    if (near) {
      if (!near.routeIds.includes(p.routeId)) near.routeIds.push(p.routeId);
      continue;
    }
    pins.push({
      key: `${p.routeId}-${p.cp.mile}`,
      lat: p.cp.lat,
      lon: p.cp.lon,
      level: p.cp.level as Level,
      title: hazard(p.cp),
      detail: "",
      routeIds: [p.routeId],
      cp: p.cp,
      routeId: p.routeId,
    });
  }
  for (const pin of pins) {
    pin.routeIds.sort();
    pin.detail = pin.routeIds.length > 1 ? `Routes ${pin.routeIds.join(", ")}` : clock(pin.cp.eta, pin.cp.tz);
  }
  const rec = trip.recommendation.route_id;
  return pins.sort((a, b) => Number(b.routeIds.includes(rec)) - Number(a.routeIds.includes(rec)) || b.level - a.level).slice(0, max);
}

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
  return pts.at(-1)![1];
}

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

/** Slider span covered by the trip, in hours from the heatmap start. */
export function tripHours(trip: Trip, r: Route): [number, number] {
  const s = trip.heatmap.start;
  return [(trip.departure - s) / HOUR, (r.arrival - s) / HOUR];
}

export interface Row {
  key: string;
  mile: number;
  place: string;
  time: string;
  weather: string;
  level: Level | null;
  why: string;
  kind: "point" | "stop" | "zone" | "end" | "warning";
}

/** Stop-by-stop rows. Compact mode keeps the ends, stops, zone changes and any weather above Low. */
export function itinerary(trip: Trip, r: Route, all: boolean): Row[] {
  const rows: Row[] = [];
  const cps = r.checkpoints;
  cps.forEach((cp, i) => {
    const prev = cps[i - 1];
    if (prev && prev.tz !== cp.tz) {
      rows.push({ key: `z${i}`, mile: (prev.mile + cp.mile) / 2, place: `Into ${zoneName(cp.eta, cp.tz)}`, time: "Clocks change here", weather: "", level: null, why: "", kind: "zone" });
    }
    const end = i === 0 || i === cps.length - 1;
    const near = (cp.level ?? 0) > 0 || (cps[i - 1]?.level ?? 0) > 0 || (cps[i + 1]?.level ?? 0) > 0;
    if (!all && !end && !near && cp.mile % 100 !== 0) return;
    rows.push({
      key: `c${i}`,
      mile: cp.mile,
      place: i === 0 ? short(trip.origin.label) : i === cps.length - 1 ? short(trip.destination.label) : (cp.place ?? `Mile ${Math.round(cp.mile)}`),
      time: when(cp.eta, cp.tz),
      weather: reading(cp),
      level: cp.level,
      why: why(cp),
      kind: end ? "end" : "point",
    });
  });
  for (const s of r.stops) {
    rows.push({
      key: `s${s.mile}`,
      mile: s.mile,
      place: s.kind === "break" ? "30-min break" : "10-h rest",
      time: `${when(s.arrive, s.tz)} → ${when(s.depart, s.tz, { day: s.depart - s.arrive > 12 * HOUR })}`,
      weather: "",
      level: null,
      why: s.kind === "break" ? "Required after 8 h driving" : "Required after 11 h driving",
      kind: "stop",
    });
  }
  for (const { warning, hit } of warningsOn(trip, r.id)) {
    rows.push({
      key: `w${warning.id}`,
      mile: hit.from_mi - 0.01,
      place: `Into ${warning.event}`,
      time: when(hit.enter, hit.tz),
      weather: "",
      level: null,
      why: "Official warning",
      kind: "warning",
    });
  }
  return rows.sort((a, b) => a.mile - b.mile);
}

/** "Dallas, Texas, United States" → "Dallas, Texas" */
export const short = (label: string) => label.replace(/, United States( of America)?$/, "");

/** Warnings that matter to a truck on this route, in the order the API ranked them. */
export function warningsOn(trip: Trip, routeId: string, relevant = true): { warning: Warning; hit: WarningHit }[] {
  return trip.warnings.flatMap((warning) => {
    const hit = warning.routes.find((h) => h.route_id === routeId);
    return hit && warning.relevant === relevant ? [{ warning, hit }] : [];
  });
}

/** "Raton Pass, Trinidad and 1 more" */
export function shortArea(area: string): string {
  const parts = area.split(";").map((p) => p.trim()).filter(Boolean);
  return parts.length <= 2 ? parts.join(" and ") : `${parts.slice(0, 2).join(", ")} and ${parts.length - 2} more`;
}

export const levelName = (l: Level | null) => (l === null ? "" : LEVEL_NAMES[l]);
