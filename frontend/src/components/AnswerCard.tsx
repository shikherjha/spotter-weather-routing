import type { Trip } from "../api/types";
import { duration, longWhen } from "../lib/time";
import { leaveLater, routeStatus, shortArea, verdict, warningsOn } from "../lib/trip";
import { useUi } from "../state";
import { AlertIcon, CheckIcon, Shield, WarnIcon } from "./bits";

export function TripLine({ trip, onEdit }: { trip: Trip; onEdit: () => void }) {
  const short = (label: string) => label.split(",")[0];
  return (
    <div className="flex items-start justify-between gap-3">
      <div className="num flex min-w-0 flex-col gap-0.5">
        <span className="truncate text-[15px] font-bold">
          {short(trip.origin.label)} → {short(trip.destination.label)}
        </span>
        <span className="text-[13px] text-ink-2">
          {longWhen(trip.departure, trip.origin_tz)} · {trip.load_lb.toLocaleString("en-US")} lb
        </span>
      </div>
      <button type="button" onClick={onEdit} className="h-9 shrink-0 rounded-lg border border-rule px-3 text-sm font-semibold max-md:h-11">
        Edit
      </button>
    </div>
  );
}

export function DemoNote({ trip }: { trip: Trip }) {
  if (trip.weather_model !== "demo-storm") return null;
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

export function RouteList({ trip }: { trip: Trip }) {
  const { selected, select, openPanel, panel } = useUi();
  return (
    <ul aria-label="Routes" className="m-0 flex list-none flex-col gap-1 p-0">
      {trip.routes.map((r) => {
        const on = r.id === selected;
        const s = routeStatus(trip, r);
        const tone = s.tone === "good" ? "text-accent" : s.tone === "bad" ? "text-severe" : "text-ink-2";
        return (
          <li key={r.id}>
            <button
              type="button"
              aria-pressed={on}
              onClick={() => (on ? openPanel(panel ? null : "stops") : select(r.id))}
              className={`flex h-11 w-full items-center gap-2.5 rounded-[10px] px-2.5 text-left ${on ? "bg-tint" : "hover:bg-tint/60"}`}
            >
              <Shield id={r.id} on={on} size={20} />
              <span className="num w-24 text-[15px] font-semibold">{duration(r.duration_s)}</span>
              <span className={`flex-1 text-right text-sm font-semibold ${tone}`}>{s.text}</span>
              <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true" fill="none" stroke="var(--ink-2)" strokeWidth="1.6">
                <path d="M5 2.5 L9.5 7 L5 11.5" />
              </svg>
            </button>
          </li>
        );
      })}
    </ul>
  );
}

export function LeaveLater({ trip, onReplan, busy }: { trip: Trip; onReplan: (departure: number) => void; busy: boolean }) {
  const l = leaveLater(trip);
  if (!l) return null;
  return (
    <button
      type="button"
      disabled={busy}
      onClick={() => onReplan(l.departure)}
      className="flex flex-col items-start gap-0.5 rounded-[10px] border-[1.5px] border-ink px-3.5 py-2.5 text-left disabled:opacity-60"
    >
      <span className="text-[15px] font-bold">{busy ? "Planning…" : l.title}</span>
      <span className="num text-[13px] text-ink-2">{l.sub}</span>
    </button>
  );
}

/** The most important official warning on the selected route, one tap from its full text. */
export function WarningLink({ trip }: { trip: Trip }) {
  const { selected, openPanel } = useUi();
  const routeId = selected ?? trip.recommendation.route_id;
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
      <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true" fill="none" stroke="var(--ink-2)" strokeWidth="1.6">
        <path d="M5 2.5 L9.5 7 L5 11.5" />
      </svg>
    </button>
  );
}
