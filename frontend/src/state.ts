import { create } from "zustand";

import type { Checkpoint, Stop } from "./api/types";
import type { Theme } from "./lib/risk";

export type Panel = "stops" | "timeline" | null;

/** Map layers a driver can switch on; the weather heatmap is `weatherOn`. */
export type Layer = "warnings" | "truckStops" | "restAreas" | "weigh";
const NO_LAYERS: Record<Layer, boolean> = { warnings: false, truckStops: false, restAreas: false, weigh: false };

export interface Focus {
  routeId: string;
  cp: Checkpoint;
}

interface UiState {
  /** Hours from the heatmap start shown on the map. */
  hour: number;
  weatherOn: boolean;
  playing: boolean;
  /** Picked route; null means the recommended one. */
  selected: string | null;
  panel: Panel;
  focus: Focus | null;
  /** The break or rest whose card is open. */
  stop: Stop | null;
  layers: Record<Layer, boolean>;
  theme: Theme;

  setHour: (h: number) => void;
  setWeather: (on: boolean) => void;
  setPlaying: (on: boolean) => void;
  select: (routeId: string) => void;
  openPanel: (p: Panel) => void;
  setFocus: (f: Focus | null) => void;
  openStop: (s: Stop | null) => void;
  toggleLayer: (l: Layer) => void;
  toggleTheme: () => void;
  resetView: () => void;
}

/** The theme index.html applied before React loaded (saved choice, else the system setting). */
const initialTheme = (): Theme => (document.documentElement.dataset.theme === "dark" ? "dark" : "light");

export const useUi = create<UiState>((set) => ({
  hour: 0,
  weatherOn: false,
  playing: false,
  selected: null,
  panel: null,
  focus: null,
  stop: null,
  // Home opens on today's warnings; a trip opens calm, on its answer.
  layers: { ...NO_LAYERS, warnings: true },
  theme: initialTheme(),

  // Moving the time means you want to see the weather at that time.
  setHour: (hour) => set({ hour, weatherOn: true }),
  setWeather: (weatherOn) => set((s) => ({ weatherOn, playing: weatherOn && s.playing })),
  setPlaying: (playing) => set((s) => ({ playing, weatherOn: playing || s.weatherOn })),
  select: (selected) => set((s) => (s.selected === selected ? {} : { selected, focus: null })),
  openPanel: (panel) => set({ panel, focus: null }),
  setFocus: (focus) => set({ focus, stop: null }),
  openStop: (stop) => set({ stop, focus: null }),
  toggleLayer: (l) => set((s) => ({ layers: { ...s.layers, [l]: !s.layers[l] } })),
  toggleTheme: () =>
    set((s) => {
      const theme = s.theme === "light" ? "dark" : "light";
      document.documentElement.dataset.theme = theme;
      try {
        localStorage.setItem("theme", theme);
      } catch {
        // Storage blocked: the choice lasts for this visit only.
      }
      return { theme };
    }),
  resetView: () =>
    set({ selected: null, hour: 0, weatherOn: false, playing: false, panel: null, focus: null, stop: null, layers: NO_LAYERS }),
}));
