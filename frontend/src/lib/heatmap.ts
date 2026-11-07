import type { Heatmap } from "../api/types";

const decoded = new WeakMap<Heatmap, Uint8Array>();

/** Risk level per [cell * hours + hour]; 255 = no data. Decoded once per trip and shared. */
export function heatmapRisk(h: Heatmap): Uint8Array {
  let bytes = decoded.get(h);
  if (!bytes) {
    bytes = Uint8Array.from(atob(h.risk), (c) => c.charCodeAt(0));
    decoded.set(h, bytes);
  }
  return bytes;
}
