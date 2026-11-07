export const MAX_LOAD_LB = 120_000;

/** "42,000", "42000 lb" or "42k" → pounds; NaN if it isn't a weight. */
export function parseLoad(text: string): number {
  const m = text.trim().replace(/,/g, "").match(/^(\d+(?:\.\d+)?)\s*(k)?\s*(lbs?)?$/i);
  return m ? Number(m[1]) * (m[2] ? 1000 : 1) : NaN;
}
