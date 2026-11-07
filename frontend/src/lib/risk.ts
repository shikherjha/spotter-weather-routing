import type { Checkpoint, Level } from "../api/types";

export type Theme = "light" | "dark";
export type RGB = [number, number, number];

export const LEVEL_NAMES = ["Low", "Moderate", "High", "Severe", "No Travel"] as const;

const hex = (h: string): RGB => [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)];

/** Map colours per level. Low is green so it never blends into the land. Keep in step with --risk-* in index.css. */
export const RISK_HEX: Record<Theme, readonly string[]> = {
  light: ["#8CC27E", "#E3A920", "#E07B39", "#C62F2B", "#4A0D1E"],
  dark: ["#4F8A47", "#E9B949", "#E8833F", "#E5483C", "#B23A55"],
};
export const RISK_RGB: Record<Theme, RGB[]> = {
  light: RISK_HEX.light.map(hex),
  dark: RISK_HEX.dark.map(hex),
};
/** Heatmap opacity per level: calm hexes stay faint so storms stand out. */
export const HEAT_ALPHA = [50, 140, 185, 215, 230];

export const THEME_RGB: Record<Theme, { accent: RGB; alt: RGB; halo: RGB; ink: RGB }> = {
  light: { accent: hex("#1F5FD1"), alt: hex("#8A939E"), halo: [255, 255, 255], ink: hex("#15191E") },
  dark: { accent: hex("#5B9BFF"), alt: hex("#6B7682"), halo: hex("#0F1216"), ink: hex("#E6E9ED") },
};

type Factor = "wind" | "rain" | "snow";

const SHORT: Record<Factor, readonly string[]> = {
  wind: ["Calm", "Breezy", "Strong wind", "Severe wind", "Unsafe wind"],
  rain: ["Dry", "Rain", "Heavy rain", "Very heavy rain", "Extreme rain"],
  snow: ["Dry", "Light snow", "Snow", "Heavy snow", "Extreme snow"],
};

export function mainFactor(cp: Checkpoint): Factor {
  return cp.drivers[0] ?? "wind";
}

/** Two-word hazard name for pins and route rows: "Heavy snow", "Unsafe wind". */
export function hazard(cp: Checkpoint): string {
  if (cp.level === null) return "No forecast yet";
  return SHORT[mainFactor(cp)][cp.level];
}

// The brief's bands (backend/engine/rules.py), used to explain a level in words.
const BANDS: Record<Factor, readonly string[]> = {
  wind: ["under 25 mph", "25–34 mph", "35–44 mph", "45–54 mph", "55+ mph"],
  rain: ["under 0.10 in/hr", "0.10–0.25 in/hr", "0.25–0.50 in/hr", "0.50–1.00 in/hr", "over 1.00 in/hr"],
  snow: ["under 0.5 in/hr", "0.5–1 in/hr", "1–2 in/hr", "2–3 in/hr", "over 3 in/hr"],
};

/** Why a checkpoint got its level, in words: "Snow 2–3 in/hr", "Wind 35–44 mph with over 40,000 lb". */
export function levelReason(cp: Checkpoint): string {
  if (cp.level === null) return "Beyond the forecast";
  if (cp.level === 0) return "";
  const f = mainFactor(cp);
  if (f === "wind" && cp.load_escalated) {
    return cp.level === 4 ? "Wind 45–54 mph, load over 30,000 lb" : "Wind 35–44 mph, load over 40,000 lb";
  }
  return `${f[0].toUpperCase()}${f.slice(1)} ${BANDS[f][cp.level]}`;
}

/** The reading that matters most at a checkpoint: "Snow 2.2 in/hr", "Wind 46 mph, gusts 64". */
export function mainReading(cp: Checkpoint): string {
  const f = mainFactor(cp);
  if (cp.level && f === "snow" && cp.snow_in_hr !== null) return `Snow ${cp.snow_in_hr.toFixed(1)} in/hr`;
  if (cp.level && f === "rain" && cp.rain_in_hr !== null) return `Rain ${cp.rain_in_hr.toFixed(2)} in/hr`;
  if (cp.wind_mph === null) return "No data";
  const gust = cp.gust_mph !== null && cp.gust_mph > cp.wind_mph + 5 ? `, gusts ${Math.round(cp.gust_mph)}` : "";
  return `Wind ${Math.round(cp.wind_mph)} mph${gust}`;
}

export function isBad(level: Level | null): boolean {
  return level !== null && level >= 2;
}
