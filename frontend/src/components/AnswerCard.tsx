// Parts of the answer card. The desktop stacks them in one floating card; the phone layout
// puts the map between the verdict and the route list.
import { DEMO_WEATHER, type Trip } from "../api/types";
import { cityName, routeById } from "../lib/route";
import { leaveLater, routeStatus, shortArea, verdict, warningsOn } from "../lib/summary";
import { duration, longWhen } from "../lib/time";
import { truckNote } from "../lib/truck";
import { useUi } from "../state";
import { AlertIcon, BackIcon, CheckIcon, ChevronIcon, WarnIcon } from "./icons";
import { Shield } from "./ui";

export function TripLine({ trip, onEdit, onBack }: { trip: Trip; onEdit: () => void; onBack: () => void }) {
  const note = truckNote(trip.height_ft, trip.hazmat);
  return (
    <div className="flex items-start gap-1.5">
      <button type="button" aria-label="Back to search" onClick={onBack} className="-ml-2 grid size-9 shrink-0 place-items-center max-lg:size-11">
        <BackIcon />
      </button>
      <div className="num flex min-w-0 flex-1 flex-col gap-0.5 pt-0.5">
        <span className="truncate text-[15px] font-bold">
          {cityName(trip.origin.label)} → {cityName(trip.destination.label)}
        </span>
        <span className="text-[13px] text-ink-2">
          {longWhen(trip.departure, trip.origin_tz)} · {trip.load_lb.toLocaleString("en-US")} lb
          {note && ` · ${note}`}
        </span>
      </div>
      <button type="button" onClick={onEdit} className="h-9 shrink-0 rounded-lg border border-rule px-3 text-sm font-semibold max-lg:h-11 max-lg:rounded-full max-lg:border-0 max-lg:bg-tint">
        Edit
      </button>
    </div>
  );
}

export function DemoNote({ trip }: { trip: Trip }) {
  if (trip.weather_model !== DEMO_WEATHER) return null;
  return (
    <p className="m-0 rounded-lg bg-tint px-3 py-2 text-[13px] leading-5 text-ink-2">
      <strong className="text-ink">Simulated storm.</strong> This trip uses made-up weather for a demo, not a real forecast.
    </p>
  );
}

export function Verdict({ trip }: { trip: Trip }) {
  const v = verdict(trip);
  return (
    <div className="flex flex-col gap-1.5">
      <span className="flex items-center gap-1.5 text-[13px] font-semibold text-ink-2">
        {v.advice === "go" ? <CheckIcon /> : <WarnIcon />} {v.label}
      </span>
      <h1 className="m-0 text-[28px] leading-[34px] font-bold">{v.headline}</h1>
      <p className="m-0 text-[15px] leading-[22px]">{v.sentence}</p>
    </div>
  );
}

/** One row per route. The first tap picks a route; tapping the picked one opens its details. */
export function RouteList({ trip }: { trip: Trip }) {
  const picked = routeById(trip, useUi((s) => s.selected)).id;
  const select = useUi((s) => s.select);
  const openPanel = useUi((s) => s.openPanel);
  return (
    <ul aria-label="Routes" className="m-0 flex list-none flex-col gap-1 p-0">
      {trip.routes.map((r) => {
        const on = r.id === picked;
        const status = routeStatus(trip, r);
        const tone = status.tone === "good" ? "text-accent" : status.tone === "bad" ? "text-severe" : "text-ink-2";
        return (
          <li key={r.id}>
            <button
              type="button"
              aria-pressed={on}
              onClick={() => (on ? openPanel("stops") : select(r.id))}
              className={`flex h-11 w-full items-center gap-2.5 rounded-[10px] px-2.5 text-left ${on ? "bg-tint" : "hover:bg-tint/60"}`}
            >
              <Shield id={r.id} on={on} size={20} />
              <span className="num w-24 text-[15px] font-semibold">{duration(r.duration_s)}</span>
              <span className={`flex-1 text-right text-sm font-semibold ${tone}`}>{status.text}</span>
              <span className="sr-only">{on ? ", show details" : ", pick this route"}</span>
              <ChevronIcon />
            </button>
          </li>
        );
      })}
    </ul>
  );
}

/** The phone's route list: three cards side by side. The first tap picks; tapping the picked one opens its stops. */
export function RouteCards({ trip }: { trip: Trip }) {
  const picked = routeById(trip, useUi((s) => s.selected)).id;
  const select = useUi((s) => s.select);
  const openPanel = useUi((s) => s.openPanel);
  return (
    <ul aria-label="Routes" className="m-0 grid list-none grid-cols-3 gap-1.5 p-0">
      {trip.routes.map((r) => {
        const on = r.id === picked;
        const status = routeStatus(trip, r);
        const tone = status.tone === "good" ? "text-accent" : status.tone === "bad" ? "text-severe" : "text-ink-2";
        return (
          <li key={r.id}>
            <button
              type="button"
              aria-pressed={on}
              onClick={() => (on ? openPanel("stops") : select(r.id))}
              className={`flex h-full w-full flex-col items-start gap-0.5 rounded-xl border-[1.5px] px-2.5 py-2 text-left ${on ? "border-accent bg-tint" : "border-rule"}`}
            >
              <span className="flex items-center gap-1">
                <Shield id={r.id} on={on} size={15} />
                <span className="num text-[13px] font-bold whitespace-nowrap">{duration(r.duration_s)}</span>
              </span>
              <span className={`text-[13px] leading-[17px] font-semibold ${tone}`}>{status.text}</span>
              <span className="sr-only">{on ? ", show its stops" : ", pick this route"}</span>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

export function LeaveLater({
  trip,
  onReplan,
  busy,
  error,
}: {
  trip: Trip;
  onReplan: (departure: number) => void;
  busy: boolean;
  error: string | null;
}) {
  const suggestion = leaveLater(trip);
  if (!suggestion) return null;
  return (
    <div className="flex flex-col gap-1.5">
      <button
        type="button"
        disabled={busy}
        onClick={() => onReplan(suggestion.departure)}
        className="flex flex-col items-start gap-0.5 rounded-[10px] border-[1.5px] border-ink px-3.5 py-2.5 text-left disabled:opacity-60"
      >
        <span className="text-[15px] font-bold">{busy ? "Planning…" : suggestion.title}</span>
        <span className="num text-[13px] text-ink-2">{suggestion.sub}</span>
      </button>
      {error && (
        <p role="alert" className="m-0 text-[13px] text-severe">
          {error}
        </p>
      )}
    </div>
  );
}

/** The most important official warning on the picked route, one tap from its full text. */
export function WarningLink({ trip }: { trip: Trip }) {
  const routeId = routeById(trip, useUi((s) => s.selected)).id;
  const openPanel = useUi((s) => s.openPanel);
  if (trip.warnings_status === "unavailable") {
    return <p className="m-0 text-[13px] text-ink-2">Official weather warnings are unavailable right now.</p>;
  }
  const found = warningsOn(trip, routeId);
  if (!found.length) return null;
  const { warning } = found[0];
  const more = found.length - 1;
  return (
    <button type="button" onClick={() => openPanel("stops")} className="flex min-h-11 items-center gap-2 text-left text-sm font-semibold">
      <AlertIcon />
      <span className="flex-1">
        {warning.event} for {shortArea(warning.area)}
        {more > 0 && <span className="font-normal text-ink-2"> · {more} more</span>}
      </span>
      <ChevronIcon />
    </button>
  );
}
