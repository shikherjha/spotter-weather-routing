// The few plain sentences and markers the first screen shows.
import type { Checkpoint, Level, Route, Trip, Warning, WarningHit } from "../api/types";
import { hazard, isBad } from "./risk";
import { arrivalTz, firstUnforecast, km, routeById, worstCheckpoint } from "./route";
import { clock, duration, when } from "./time";

export type Tone = "good" | "bad" | "plain";

const PIN_MERGE_KM = 60; // stretches this close with the same hazard are one place on the map
const MAX_PINS = 4;

/** One or two words per route for the route list: "Safest", "Unsafe wind", "33 m slower". */
export function routeStatus(trip: Trip, r: Route): { text: string; tone: Tone } {
  if (r.recommended) return { text: trip.routes.length > 1 ? "Safest" : "Only route", tone: "good" };
  const worst = worstCheckpoint(r);
  if (worst && isBad(worst.level)) return { text: hazard(worst), tone: (worst.level ?? 0) >= 3 ? "bad" : "plain" };
  if (r.score.unknown_mi > 0) return { text: "Forecast incomplete", tone: "plain" };
  const rec = routeById(trip, trip.recommendation.route_id);
  const extra = r.duration_s - rec.duration_s;
  return { text: extra >= 60 ? `${duration(extra)} slower` : "Also clear", tone: "plain" };
}

export function verdict(trip: Trip) {
  const rec = routeById(trip, trip.recommendation.route_id);
  const worst = worstCheckpoint(rec);
  const gap = firstUnforecast(rec);
  const advice = trip.recommendation.advice;
  const label = advice === "go" ? "Good to go" : advice === "caution" ? "Drive with caution" : "Wait if you can";
  const n = trip.routes.length;
  let sentence: string;
  if (advice === "delay") {
    sentence = `Every route crosses No Travel weather. Route ${rec.id} has the least of it.`;
  } else if (!worst || !isBad(worst.level)) {
    sentence = gap
      ? `Clear weather as far as the forecast goes, to mile ${Math.round(gap.mile)}.`
      : n > 1
        ? `Clear weather the whole way, and the fastest safe option of ${n}.`
        : "Clear weather the whole way.";
  } else {
    const at = `${hazard(worst)}${worst.place ? ` near ${worst.place}` : ""} around ${when(worst.eta, worst.tz)}`;
    sentence =
      advice === "caution"
        ? `${at}, but ${n > 1 ? `it's still the safest of the ${n}` : "it's the only route found"}.`
        : `${at}; nothing worse than High on the way.`;
  }
  if (gap && worst && isBad(worst.level)) sentence += ` No forecast yet past mile ${Math.round(gap.mile)}.`;
  return { label, headline: `Take Route ${rec.id}`, sentence, advice };
}

/** The departure advisor's suggestion, if waiting is actually safer. */
export function leaveLater(trip: Trip) {
  const { best_offset_h: offset, options } = trip.departure_advice;
  if (offset <= 0) return null;
  const opt = options.find((o) => o.offset_h === offset);
  if (!opt) return null;
  const clear = opt.no_travel_mi === 0 && opt.severe_mi === 0 && opt.high_mi === 0;
  const outlook = !clear ? "Less bad weather" : opt.unknown_mi > 0 ? "Clear as far as the forecast goes" : "Clear all the way";
  return {
    departure: opt.departure,
    title: `Leave ${when(opt.departure, trip.origin_tz, { zone: false })} instead`,
    sub: `${outlook} · arrive ${when(opt.departure + opt.duration_s, arrivalTz(routeById(trip, opt.route_id)))}`,
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

/** One pin per stretch of High-or-worse weather; stretches shared by several routes merge into one pin. */
export function troubleSpots(trip: Trip): Pin[] {
  const peaks: { cp: Checkpoint & { level: Level }; routeId: string }[] = [];
  for (const r of trip.routes) {
    let peak: (Checkpoint & { level: Level }) | null = null;
    for (const cp of [...r.checkpoints, null]) {
      if (cp && cp.level !== null && isBad(cp.level)) {
        if (!peak || cp.level > peak.level) peak = { ...cp, level: cp.level };
      } else if (peak) {
        peaks.push({ cp: peak, routeId: r.id });
        peak = null;
      }
    }
  }
  const pins: Pin[] = [];
  for (const { cp, routeId } of peaks.sort((a, b) => b.cp.level - a.cp.level)) {
    const near = pins.find((p) => km(p, cp) < PIN_MERGE_KM && hazard(p.cp) === hazard(cp));
    if (near) {
      if (!near.routeIds.includes(routeId)) near.routeIds.push(routeId);
      continue;
    }
    pins.push({ key: `${routeId}-${cp.mile}`, lat: cp.lat, lon: cp.lon, level: cp.level, title: hazard(cp), detail: "", routeIds: [routeId], cp, routeId });
  }
  for (const pin of pins) {
    pin.routeIds.sort();
    pin.detail = pin.routeIds.length > 1 ? `Routes ${pin.routeIds.join(", ")}` : clock(pin.cp.eta, pin.cp.tz);
  }
  const rec = trip.recommendation.route_id;
  const onRec = (p: Pin) => Number(p.routeIds.includes(rec));
  return pins.sort((a, b) => onRec(b) - onRec(a) || b.level - a.level).slice(0, MAX_PINS);
}

/** Warnings on this route, split by whether Jev judged them to matter to a truck. In the API's order. */
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
