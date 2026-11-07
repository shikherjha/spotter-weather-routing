import { create } from "zustand";

import type { Checkpoint } from "./api/types";
import type { Theme } from "./lib/risk";

export type Panel = "stops" | "timeline" | null;

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
  theme: Theme;

  setHour: (h: number) => void;
  setWeather: (on: boolean) => void;
  setPlaying: (on: boolean) => void;
  select: (routeId: string) => void;
  openPanel: (p: Panel) => void;
  setFocus: (f: Focus | null) => void;
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
  theme: initialTheme(),

  // Moving the time means you want to see the weather at that time.
  setHour: (hour) => set({ hour, weatherOn: true }),
  setWeather: (weatherOn) => set((s) => ({ weatherOn, playing: weatherOn && s.playing })),
  setPlaying: (playing) => set((s) => ({ playing, weatherOn: playing || s.weatherOn })),
  select: (selected) => set((s) => (s.selected === selected ? {} : { selected, focus: null })),
  openPanel: (panel) => set({ panel, focus: null }),
  setFocus: (focus) => set({ focus }),
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
  resetView: () => set({ selected: null, hour: 0, weatherOn: false, playing: false, panel: null, focus: null }),
}));
