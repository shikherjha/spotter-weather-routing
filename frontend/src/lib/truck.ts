// Your truck: its size choices, how it reads back, and remembering it on this device.
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

export interface MyTruck {
  load_lb: number;
  height_ft: number;
  hazmat: boolean;
}

const KEY = "my-truck";
export const DEFAULT_TRUCK: MyTruck = { load_lb: 40_000, height_ft: DEFAULT_HEIGHT_FT, hazmat: false };

export const savedTruck = (): MyTruck => ({ ...DEFAULT_TRUCK, ...readJson<Partial<MyTruck>>(KEY, {}) });
export const saveTruck = (t: MyTruck) => writeJson(KEY, t);

/** "13′ 6″ · 42,000 lb · no hazmat" */
export const truckSummary = (t: MyTruck) =>
  `${feetInches(t.height_ft)} · ${Math.round(t.load_lb).toLocaleString("en-US")} lb · ${t.hazmat ? "hazmat" : "no hazmat"}`;
