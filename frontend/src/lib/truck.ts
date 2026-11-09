// Your truck: its size choices, how it reads back, and remembering it on this device.
import { MAX_LOAD_LB } from "./load";
import { readJson, writeJson } from "./storage";

export const HEIGHTS_FT = [12.5, 13, 13.5, 14, 14.5, 15];
export const DEFAULT_HEIGHT_FT = 13.5; // a standard US van trailer

export const feetInches = (ft: number) => `${Math.floor(ft)}′ ${Math.round((ft % 1) * 12)}″`;

/** "14′ 0″ tall · Hazmat", or "" for a standard truck. */
export function truckNote(heightFt: number, hazmat: boolean): string {
  const parts = [];
  if (heightFt !== DEFAULT_HEIGHT_FT) parts.push(`${feetInches(heightFt)} tall`);
  if (hazmat) parts.push("Hazmat");
  return parts.join(" · ");
}

export interface SavedTruck {
  load_lb: number;
  height_ft: number;
  hazmat: boolean;
}

const KEY = "my-truck";
export const DEFAULT_TRUCK: SavedTruck = { load_lb: 40_000, height_ft: DEFAULT_HEIGHT_FT, hazmat: false };

/** The truck remembered on this device; any field that's missing or out of range falls back to the default. */
export function savedTruck(): SavedTruck {
  const t = (readJson(KEY) ?? {}) as Partial<Record<keyof SavedTruck, unknown>>;
  const load = typeof t.load_lb === "number" && t.load_lb > 0 && t.load_lb <= MAX_LOAD_LB ? t.load_lb : DEFAULT_TRUCK.load_lb;
  const height = typeof t.height_ft === "number" && HEIGHTS_FT.includes(t.height_ft) ? t.height_ft : DEFAULT_TRUCK.height_ft;
  return { load_lb: load, height_ft: height, hazmat: t.hazmat === true };
}

export const saveTruck = (t: SavedTruck) => writeJson(KEY, t);

/** "13′ 6″ · 42,000 lb · no hazmat" */
export const truckSummary = (t: SavedTruck) =>
  `${feetInches(t.height_ft)} · ${Math.round(t.load_lb).toLocaleString("en-US")} lb · ${t.hazmat ? "hazmat" : "no hazmat"}`;
