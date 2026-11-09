import type { CSSProperties } from "react";

import type { Trip } from "../../api/types";
import { useUi, type Layer } from "../../state";
import { ThemeIcon } from "../icons";

type Chip = { key: Layer | "weather"; name: string; dot: string };

// The dot on each switch is the marker it draws, so the switches double as the map's key.
const CHIPS: Chip[] = [
  { key: "weather", name: "Weather", dot: "rounded-full bg-[var(--risk-1)] border-[var(--risk-1)]" },
  { key: "warnings", name: "Warnings", dot: "rounded-[2px] bg-[var(--severe)]/35 border-[var(--severe)]" },
  { key: "truckStops", name: "Truck stops", dot: "rounded-[3px] bg-ink border-ink" },
  { key: "restAreas", name: "Rest areas", dot: "rounded-[3px] bg-surface border-ink" },
  { key: "weigh", name: "Weigh stations", dot: "rounded-full bg-surface border-ink" },
];

/** One switch per map layer. Weather needs a trip; the rest work anywhere. */
export function LayerChips({ trip, className = "", style }: { trip: Trip | null; className?: string; style?: CSSProperties }) {
  const layers = useUi((s) => s.layers);
  const toggleLayer = useUi((s) => s.toggleLayer);
  const weatherOn = useUi((s) => s.weatherOn);
  const setWeather = useUi((s) => s.setWeather);
  return (
    <nav aria-label="Map layers" className={`flex gap-2 ${className}`} style={style}>
      {CHIPS.map((c) => {
        if (c.key === "weather" && !trip) return null;
        const on = c.key === "weather" ? weatherOn : layers[c.key];
        return (
          <button
            key={c.key}
            type="button"
            aria-pressed={on}
            onClick={() => (c.key === "weather" ? setWeather(!weatherOn) : toggleLayer(c.key))}
            className={`flex h-11 shrink-0 items-center gap-2 rounded-full border px-3.5 text-sm font-semibold whitespace-nowrap shadow-float lg:h-[38px] ${
              on ? "border-ink bg-ink text-surface" : "border-rule bg-surface text-ink"
            }`}
          >
            <span aria-hidden="true" className={`size-2.5 border-[1.5px] ${c.dot} ${on ? "outline-[1.5px] outline-surface" : ""}`} />
            {c.name}
          </button>
        );
      })}
    </nav>
  );
}

export function ThemeButton({ className = "" }: { className?: string }) {
  const theme = useUi((s) => s.theme);
  const toggleTheme = useUi((s) => s.toggleTheme);
  return (
    <button
      type="button"
      onClick={toggleTheme}
      aria-label={theme === "light" ? "Switch to dark mode" : "Switch to light mode"}
      className={`grid size-10 shrink-0 place-items-center rounded-[10px] border border-rule bg-surface text-ink shadow-float ${className}`}
    >
      <ThemeIcon dark={theme === "dark"} />
    </button>
  );
}

/** What the small dots along a route mean; everything else is labelled on the map or its switch. */
export function MapKey() {
  return (
    <div className="num absolute right-6 bottom-9 z-10 text-xs text-ink-2">
      <span className="flex items-center gap-1.5 rounded bg-surface/85 px-1.5">
        <svg width="22" height="8" viewBox="0 0 22 8" aria-hidden="true">
          <path d="M1 4 H21" stroke="var(--accent)" strokeWidth="5" strokeLinecap="round" />
          <circle cx="6" cy="4" r="1.6" fill="var(--surface)" />
          <circle cx="16" cy="4" r="1.6" fill="var(--surface)" />
        </svg>
        Weather checked at each dot
      </span>
    </div>
  );
}
