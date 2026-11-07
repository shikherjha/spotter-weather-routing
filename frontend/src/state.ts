import { create } from "zustand";

import type { Checkpoint, TripRequest } from "./api/types";
import type { Theme } from "./lib/risk";

export type Panel = "stops" | "timeline" | null;

export interface Focus {
  routeId: string;
  cp: Checkpoint;
}

interface UiState {
  /** Hours from the heatmap start shown on the map (0..48). */
  hour: number;
  weatherOn: boolean;
  playing: boolean;
  selected: string | null;
  panel: Panel;
  focus: Focus | null;
  theme: Theme;
  /** The last request, so "Edit" and "Leave later" can re-plan from it. */
  request: TripRequest | null;

  setHour: (h: number) => void;
  setWeather: (on: boolean) => void;
  setPlaying: (on: boolean) => void;
  select: (routeId: string) => void;
  openPanel: (p: Panel) => void;
  setFocus: (f: Focus | null) => void;
  toggleTheme: () => void;
  setRequest: (r: TripRequest) => void;
  resetView: (routeId: string, hour: number) => void;
}

const savedTheme = (): Theme => {
  try {
    const t = localStorage.getItem("theme");
    if (t === "light" || t === "dark") return t;
  } catch {
    /* storage blocked: fall back to the system setting */
  }
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
};

export const useUi = create<UiState>((set) => ({
  hour: 0,
  weatherOn: false,
  playing: false,
  selected: null,
  panel: null,
  focus: null,
  theme: savedTheme(),
  request: null,

  // Moving the time means you want to see the weather at that time.
  setHour: (hour) => set({ hour, weatherOn: true }),
  setWeather: (weatherOn) => set((s) => ({ weatherOn, playing: weatherOn && s.playing })),
  setPlaying: (playing) => set((s) => ({ playing, weatherOn: playing || s.weatherOn })),
  select: (selected) => set({ selected, focus: null }),
  openPanel: (panel) => set({ panel, focus: null }),
  setFocus: (focus) => set({ focus }),
  toggleTheme: () =>
    set((s) => {
      const theme = s.theme === "light" ? "dark" : "light";
      try {
        localStorage.setItem("theme", theme);
      } catch {
        /* not persisted; fine */
      }
      return { theme };
    }),
  setRequest: (request) => set({ request }),
  resetView: (selected, hour) => set({ selected, hour, weatherOn: false, playing: false, panel: null, focus: null }),
}));
