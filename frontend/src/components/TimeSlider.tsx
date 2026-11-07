import { useEffect } from "react";

import type { Trip } from "../api/types";
import { LEVEL_NAMES } from "../lib/risk";
import { fromNow, tick, when } from "../lib/time";
import { routeById, tripHours } from "../lib/trip";
import { useUi } from "../state";
import { PlayIcon } from "./bits";

const MAX_H = 48;
const STEP_MS = 450;

export function TimeSlider({ trip, compact = false }: { trip: Trip; compact?: boolean }) {
  const { hour, setHour, playing, setPlaying, weatherOn, selected } = useUi();
  const route = routeById(trip, selected ?? trip.recommendation.route_id);
  const start = trip.heatmap.start;
  const at = start + hour * 3600;
  const [h0, h1] = tripHours(trip, route);
  const pct = (h: number) => `${(Math.min(MAX_H, Math.max(0, h)) / MAX_H) * 100}%`;

  useEffect(() => {
    if (!playing) return;
    const id = window.setInterval(() => {
      const h = useUi.getState().hour;
      if (h >= MAX_H) setPlaying(false);
      else setHour(h + 1);
    }, STEP_MS);
    return () => window.clearInterval(id);
  }, [playing, setHour, setPlaying]);

  const togglePlay = () => {
    if (!playing && hour >= MAX_H) setHour(0);
    setPlaying(!playing);
  };

  return (
    <div className="flex flex-col gap-2.5">
      {weatherOn && !compact && (
        <div className="flex flex-wrap items-center gap-x-3.5 gap-y-1 pl-1 text-[13px]">
          <span className="font-semibold">Risk for {trip.load_lb.toLocaleString("en-US")} lb</span>
          {LEVEL_NAMES.map((name, l) => (
            <span key={name} className="flex items-center gap-1.5">
              <span className={`h-2.5 w-3.5 rounded-sm risk-${l}`} style={{ background: l < 4 ? `var(--risk-${l})` : undefined }} />
              {name}
            </span>
          ))}
        </div>
      )}
      <div className="flex items-center gap-3.5">
        <button
          type="button"
          onClick={togglePlay}
          aria-label={playing ? "Pause the forecast" : "Play the forecast"}
          className="grid size-11 shrink-0 place-items-center rounded-full bg-ink text-surface"
        >
          <PlayIcon playing={playing} />
        </button>
        <label htmlFor="forecast-hour" className="num flex w-[150px] shrink-0 flex-col max-md:w-auto">
          <span className="text-xs text-ink-2">{weatherOn ? "Weather at" : "Weather"}</span>
          <span className="text-[15px] font-bold">{when(at, trip.origin_tz)}</span>
          <span className="text-xs text-ink-2">{fromNow(hour)}</span>
        </label>
        <div className="relative h-11 min-w-0 flex-1">
          <span aria-hidden="true" className="absolute inset-x-0 top-[13px] h-1.5 rounded-full bg-rule" />
          <span
            aria-hidden="true"
            className="absolute top-[13px] h-1.5"
            style={{ left: pct(h0), width: `calc(${pct(h1)} - ${pct(h0)})`, background: "var(--accent-soft)" }}
          />
          <input
            id="forecast-hour"
            type="range"
            min={0}
            max={MAX_H}
            step={1}
            value={hour}
            onChange={(e) => setHour(Number(e.target.value))}
            aria-valuetext={`${when(at, trip.origin_tz)}, ${fromNow(hour)}`}
            className="time-range absolute inset-x-0 top-1.5 m-0 h-5 w-full"
          />
          <div aria-hidden="true" className="num pointer-events-none absolute inset-x-0 top-7 text-xs text-ink-2">
            <span className="absolute left-0">Now</span>
            {h0 < MAX_H - 4 && !compact && (
              <span className="absolute font-semibold text-accent" style={{ left: `max(2.6rem, ${pct(h0)})` }}>
                Your trip
              </span>
            )}
            <span className="absolute left-1/2 -translate-x-1/2 max-md:hidden">{tick(start + 24 * 3600, trip.origin_tz, true)}</span>
            <span className="absolute right-0">{tick(start + MAX_H * 3600, trip.origin_tz, true)}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
