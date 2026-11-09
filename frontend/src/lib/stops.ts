// How breaks, rests and weigh stations read: "30-min break at Love's, Dalhart, TX".
import type { Stop, WeighStation } from "../api/types";

export const stopWhat = (s: Stop) => (s.kind === "break" ? "30-min break" : "10-h rest");

/** The place a stop is planned at: "Love's, Dalhart, TX", "Rest area near Raton, NM", or null. */
export function stopPlace(s: Stop): string | null {
  if (s.place && s.town) return s.place === "Rest area" ? `Rest area near ${s.town}` : `${s.place}, ${s.town}`;
  return s.place ?? (s.town ? `near ${s.town}` : null);
}

export function stopLabel(s: Stop): string {
  if (s.place === "Rest area") return `${stopWhat(s)} at a rest area${s.town ? ` near ${s.town}` : ""}`;
  const where = stopPlace(s);
  if (!where) return stopWhat(s);
  return where.startsWith("near ") ? `${stopWhat(s)} ${where}` : `${stopWhat(s)} at ${where}`;
}

/** The short label on the map pill: "Love's, Dalhart" (town without its state). */
export function pillLabel(s: Stop): string {
  const town = s.town?.split(",")[0];
  if (s.place && s.place !== "Rest area") return town ? `${s.place}, ${town}` : s.place;
  return town ? `Rest area, ${town}` : stopWhat(s);
}

export const pillChip = (s: Stop) => (s.kind === "break" ? "30 min" : "10 h");

export function weighLabel(w: WeighStation): string {
  const named = w.name.toLowerCase() !== "weigh station";
  if (named) return w.town ? `${w.name}, ${w.town}` : w.name;
  return w.town ? `Weigh station near ${w.town}` : "Weigh station";
}
