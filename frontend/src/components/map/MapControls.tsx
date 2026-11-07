import { useUi } from "../../state";
import { CloudIcon, ThemeIcon } from "../icons";

export function MapButtons() {
  const weatherOn = useUi((s) => s.weatherOn);
  const setWeather = useUi((s) => s.setWeather);
  const theme = useUi((s) => s.theme);
  const toggleTheme = useUi((s) => s.toggleTheme);
  return (
    <div className="absolute top-6 right-6 z-10 flex gap-2 max-lg:top-2.5 max-lg:right-2.5">
      <button
        type="button"
        aria-pressed={weatherOn}
        onClick={() => setWeather(!weatherOn)}
        className={`flex h-10 items-center gap-2 rounded-[10px] border border-rule px-3.5 text-sm font-semibold shadow-float max-lg:h-9 max-lg:px-3 ${weatherOn ? "bg-ink text-surface" : "bg-surface text-ink"}`}
      >
        <CloudIcon />
        Weather
      </button>
      <button
        type="button"
        onClick={toggleTheme}
        aria-label={theme === "light" ? "Switch to dark mode" : "Switch to light mode"}
        className="grid size-10 place-items-center rounded-[10px] border border-rule bg-surface text-ink shadow-float max-lg:size-9"
      >
        <ThemeIcon dark={theme === "dark"} />
      </button>
    </div>
  );
}

/** What the map's dots mean; the risk colours are explained by the slider's legend. */
export function MapKey() {
  return (
    <div className="num absolute right-6 bottom-9 z-10 flex flex-col items-end gap-1 text-xs text-ink-2">
      <span className="flex items-center gap-1.5 rounded bg-surface/85 px-1.5">
        <span className="size-2.5 rounded-full border-2 border-surface bg-ink" /> Break or rest stop
      </span>
      <span className="flex items-center gap-1.5 rounded bg-surface/85 px-1.5">
        <span className="size-2 rounded-full border-2 border-ink-2 bg-surface" /> Weather checked at each dot
      </span>
    </div>
  );
}
