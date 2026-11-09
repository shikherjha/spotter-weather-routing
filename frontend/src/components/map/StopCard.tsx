import type { Checkpoint, Route, Stop } from "../../api/types";
import { LEVEL_NAMES, mainReading } from "../../lib/risk";
import { stopPlace, stopWhat } from "../../lib/stops";
import { sameDay, when } from "../../lib/time";
import { CloseIcon } from "../icons";

/** The weather the driver meets at the checkpoint just before (arriving) or just after (leaving) a stop. */
function weatherNear(route: Route, mile: number, after: boolean): Checkpoint | undefined {
  const cps = route.checkpoints;
  return after ? cps.find((c) => c.mile >= mile) : [...cps].reverse().find((c) => c.mile <= mile);
}

function WeatherLine({ label, cp }: { label: string; cp: Checkpoint | undefined }) {
  if (!cp) return null;
  return (
    <>
      <dt className="text-ink-2">{label}</dt>
      <dd className="m-0 flex items-center gap-1.5">
        <span aria-hidden="true" className={`size-2.5 shrink-0 rounded-full risk-${cp.level ?? 0}`} />
        {cp.level === null ? "No forecast yet" : `${LEVEL_NAMES[cp.level]} · ${mainReading(cp).toLowerCase()}`}
      </dd>
    </>
  );
}

/** A planned break or rest: where it is, when, the weather either side, and a way to move it. */
export function StopCard({
  route,
  stop,
  onClose,
  onSkip,
  skipping,
  error,
}: {
  route: Route;
  stop: Stop;
  onClose: () => void;
  onSkip: (s: Stop) => void;
  skipping: boolean;
  error: string | null;
}) {
  const where = stopPlace(stop);
  const kind = stop.place_kind === "rest_area" ? "Rest area" : stop.place_kind === "truck_stop" ? "Truck stop" : "Roadside";
  const rest = stop.kind === "rest";
  const why = !stop.place
    ? "No truck stop or rest area within 90 minutes of the limit. Find a safe, legal place to park near here."
    : rest
      ? "The last place to park before your 11 hours of driving run out."
      : "The last place to stop before 8 hours of driving without a break.";
  const directions = `https://www.google.com/maps/dir/?api=1&destination=${stop.lat},${stop.lon}`;

  return (
    <div
      role="dialog"
      aria-label={`${stopWhat(stop)}${where ? ` at ${where}` : ""}`}
      onKeyDown={(e) => e.key === "Escape" && onClose()}
      className="flex w-[304px] flex-col gap-3 p-3.5 font-sans text-ink"
    >
      <div className="flex items-start gap-2.5">
        <span aria-hidden="true" className={`mt-1 size-3.5 shrink-0 rounded-[3px] border-2 border-ink ${stop.place_kind === "truck_stop" ? "bg-ink" : "bg-surface"}`} />
        <div className="flex min-w-0 flex-1 flex-col gap-0.5">
          <strong className="text-base leading-5">{where?.replace(/^near /, "Near ") ?? stopWhat(stop)}</strong>
          <span className="num text-[13px] text-ink-2">
            {kind} · mile {Math.round(stop.mile)} on Route {route.id}
          </span>
        </div>
        <button type="button" aria-label="Close" onClick={onClose} className="-mt-1 -mr-1 grid size-8 place-items-center text-ink-2">
          <CloseIcon size={12} />
        </button>
      </div>
      <div className="flex flex-col gap-1 rounded-[10px] bg-tint px-3 py-2.5">
        <span className="text-[13px] font-bold">Your {rest ? "10-hour rest" : "30-minute break"}</span>
        <span className="num text-sm">
          {when(stop.arrive, stop.tz)} → {when(stop.depart, stop.tz, { day: !sameDay(stop.arrive, stop.depart, stop.tz) })}
        </span>
        <span className="text-[13px] leading-[18px] text-ink-2">{why}</span>
      </div>
      <dl className="num m-0 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-sm">
        <WeatherLine label="Arrive" cp={weatherNear(route, stop.mile, false)} />
        <WeatherLine label="Leave" cp={weatherNear(route, stop.mile, true)} />
      </dl>
      <div className="flex gap-2">
        {stop.place && (
          <button
            type="button"
            onClick={() => onSkip(stop)}
            disabled={skipping}
            className="h-10 flex-[1.4] rounded-lg border border-ink text-sm font-semibold whitespace-nowrap disabled:opacity-60"
          >
            {skipping ? "Re-planning…" : rest ? "Rest somewhere else" : "Stop somewhere else"}
          </button>
        )}
        <a
          href={directions}
          target="_blank"
          rel="noreferrer"
          className="grid h-10 flex-1 place-items-center rounded-lg bg-tint text-sm font-semibold text-ink no-underline"
        >
          Directions
        </a>
      </div>
      {error && (
        <p role="alert" className="m-0 text-[13px] text-severe">
          {error}
        </p>
      )}
    </div>
  );
}
