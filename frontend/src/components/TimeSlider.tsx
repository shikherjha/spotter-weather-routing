import { useEffect } from "react";

import type { Trip } from "../api/types";
import { LEVEL_NAMES } from "../lib/risk";
import { routeById, tripHours } from "../lib/route";
import { HOUR, relativeToNow, tick, when } from "../lib/time";
import { useUi } from "../state";
import { PlayIcon } from "./icons";
import { RiskSwatch } from "./ui";

const STEP_MS = 450;

/** The 0–48 h forecast slider. A native range input over a drawn track, so keyboard and screen readers work. */
export function TimeSlider({ trip, compact = false }: { trip: Trip; compact?: boolean }) {
  const hour = useUi((s) => s.hour);
  const setHour = useUi((s) => s.setHour);
  const playing = useUi((s) => s.playing);
  const setPlaying = useUi((s) => s.setPlaying);
  const weatherOn = useUi((s) => s.weatherOn);
  const route = routeById(trip, useUi((s) => s.selected));

  const { start, hours } = trip.heatmap;
  const last = hours - 1;
  const at = start + hour * HOUR;
  const [h0, h1] = tripHours(trip, route);
  const pct = (h: number) => `${(Math.min(last, Math.max(0, h)) / last) * 100}%`;

  useEffect(() => {
    if (!playing) return;
    const id = window.setInterval(() => {
      const h = useUi.getState().hour;
      if (h >= last) setPlaying(false);
      else setHour(h + 1);
    }, STEP_MS);
    return () => window.clearInterval(id);
  }, [playing, last, setHour, setPlaying]);

  const togglePlay = () => {
    if (!playing && hour >= last) setHour(0);
    setPlaying(!playing);
  };

  const track = (
    <div className="relative h-11 min-w-0 flex-1">
      <span aria-hidden="true" className="absolute inset-x-0 top-[13px] h-1.5 rounded-full bg-rule" />
      <span
        aria-hidden="true"
        className="absolute top-[13px] h-1.5 bg-[var(--accent-soft)]"
        style={{ left: pct(h0), width: `calc(${pct(h1)} - ${pct(h0)})` }}
      />
      <input
        id="forecast-hour"
        type="range"
        min={0}
        max={last}
        step={1}
        value={hour}
        onChange={(e) => setHour(Number(e.target.value))}
        aria-valuetext={`${when(at, trip.origin_tz)}, ${relativeToNow(at)}`}
        className="time-range absolute inset-x-0 top-1.5 m-0 h-5 w-full"
      />
      <div aria-hidden="true" className="num pointer-events-none absolute inset-x-0 top-7 text-xs text-ink-2">
        <span className="absolute left-0">{tick(start, trip.origin_tz, true)}</span>
        {!compact && h0 < last - 4 && (
          <span className="absolute font-semibold text-accent" style={{ left: `max(4.5rem, ${pct(h0)})` }}>
            Your trip
          </span>
        )}
        <span className="absolute left-1/2 -translate-x-1/2 max-md:hidden">{tick(start + (last / 2) * HOUR, trip.origin_tz, true)}</span>
        <span className="absolute right-0">{tick(start + last * HOUR, trip.origin_tz, true)}</span>
      </div>
    </div>
  );

  return (
    <div className="flex flex-col gap-2.5">
      {weatherOn && (
        <div className="flex flex-wrap items-center gap-x-3.5 gap-y-1 pl-1 text-[13px]">
          <span className="font-semibold">Risk for {trip.load_lb.toLocaleString("en-US")} lb</span>
          {LEVEL_NAMES.map((name, l) => (
            <span key={name} className="flex items-center gap-1.5">
              <RiskSwatch level={l} className="h-2.5 w-3.5 rounded-sm" />
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
        {compact ? (
          <div className="flex min-w-0 flex-1 flex-col">
            <label htmlFor="forecast-hour" className="num truncate text-[13px]">
              <strong>{weatherOn ? "Weather at" : "Weather"}</strong>{" "}
              <span className="text-ink-2">
                · {when(at, trip.origin_tz)}, {relativeToNow(at).toLowerCase()}
              </span>
            </label>
            {track}
          </div>
        ) : (
          <>
            <label htmlFor="forecast-hour" className="num flex w-[150px] shrink-0 flex-col max-md:w-auto">
              <span className="text-xs text-ink-2">{weatherOn ? "Weather at" : "Weather"}</span>
              <span className="text-[15px] font-bold">{when(at, trip.origin_tz)}</span>
              <span className="text-xs text-ink-2">{relativeToNow(at)}</span>
            </label>
            {track}
          </>
        )}
      </div>
    </div>
  );
}
