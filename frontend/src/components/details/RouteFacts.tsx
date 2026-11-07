import type { Route, Trip } from "../../api/types";
import { LEVEL_NAMES } from "../../lib/risk";
import { shortArea, warningsOn } from "../../lib/summary";
import { duration, when } from "../../lib/time";
import { AlertIcon } from "../icons";
import { RiskSwatch } from "../ui";

/** Official NWS warnings on the route, in the alert's own words. */
export function Warnings({ trip, route }: { trip: Trip; route: Route }) {
  if (trip.warnings_status === "unavailable") {
    return <p className="m-0 text-sm text-ink-2">Official weather warnings are unavailable right now. Check weather.gov before you leave.</p>;
  }
  const relevant = warningsOn(trip, route.id);
  const setAside = warningsOn(trip, route.id, false);
  if (!relevant.length && !setAside.length) return null;
  return (
    <div className="flex flex-col gap-4 border-b border-rule pb-5">
      {relevant.map(({ warning, hit }) => (
        <article key={warning.id} className="flex flex-col gap-1.5">
          <h3 className="m-0 flex items-center gap-2 text-[15px] font-bold">
            <AlertIcon /> {warning.event}
          </h3>
          <p className="num m-0 text-sm leading-[21px]">
            {shortArea(warning.area)}
            {warning.ends && <>, until {when(warning.ends, hit.tz)}</>}. You'd reach it {when(hit.enter, hit.tz)}, miles {Math.round(hit.from_mi)}–
            {Math.round(hit.to_mi)}.
          </p>
          <p className="m-0 text-sm leading-[21px]">{warning.summary}</p>
          {warning.road_closure && <span className="self-start rounded bg-tint px-2 py-0.5 text-xs font-bold text-severe">Roads may close</span>}
          <span className="text-xs text-ink-2">
            {warning.source === "simulated" ? (
              "Simulated warning for the demo storm"
            ) : warning.url ? (
              <a href={warning.url} target="_blank" rel="noreferrer" className="text-ink-2 underline">
                National Weather Service
              </a>
            ) : (
              "National Weather Service"
            )}
            {warning.triage === "jev" ? " · relevance checked by Jev (TypeSafe AI)" : ""}
          </span>
        </article>
      ))}
      {setAside.length > 0 && (
        <p className="m-0 text-[13px] leading-5 text-ink-2">
          Also in effect, not a driving hazard: {setAside.map(({ warning }) => warning.event).join(", ")}.
        </p>
      )}
    </div>
  );
}

const CRITERION_PHRASE: Record<string, string> = {
  no_travel_mi: "of No Travel weather",
  severe_mi: "of Severe weather",
  high_mi: "of High weather",
  avg_risk: "average risk",
  duration_s: "of driving",
};

function formatValue(criterion: string | null, v: number | null): string {
  if (v === null) return "—";
  if (criterion === "duration_s") return duration(v);
  if (criterion === "avg_risk") return v.toFixed(2);
  return `${Math.round(v)} mi`;
}

/** "Route A has 25 mi of No Travel weather; this one has 0 mi." */
function comparison(subject: string, loser: Route, winnerName: string): string {
  const d = loser.lost_on;
  if (!d) return `${subject} is equally good.`;
  const phrase = CRITERION_PHRASE[d.criterion ?? ""] ?? d.label;
  return `${subject} has ${formatValue(d.criterion, d.this_value)} ${phrase}; ${winnerName} has ${formatValue(d.criterion, d.winner_value)}.`;
}

/** Why this route won (or lost), then how its miles split across risk levels. */
export function WhyRoute({ trip, route }: { trip: Trip; route: Route }) {
  const others = trip.routes.filter((r) => r.id !== route.id);
  const miles = route.score.miles_by_level;
  return (
    <>
      <div className="flex flex-col gap-1.5">
        <span className="text-[15px] font-bold">{route.recommended ? `Why Route ${route.id}` : `Why not Route ${route.id}`}</span>
        {route.recommended ? (
          others.map((o) => (
            <span key={o.id} className="num text-sm leading-[21px]">
              {comparison(`Route ${o.id}`, o, "this one")}
            </span>
          ))
        ) : (
          <span className="num text-sm leading-[21px]">{comparison("It", route, `Route ${trip.recommendation.route_id}`)}</span>
        )}
        <span className="text-xs leading-[17px] text-ink-2">
          We rank by miles in No Travel, then Severe, then High weather, then average risk, then drive time.
        </span>
      </div>
      <div className="flex flex-col gap-2 border-t border-rule pt-5">
        <span className="text-[15px] font-bold">Miles by risk</span>
        <div className="flex h-2.5 overflow-hidden rounded-full" role="img" aria-label="Share of miles at each risk level">
          {miles.map((v, l) => (
            <span key={l} style={{ width: `${(v / route.distance_mi) * 100}%` }}>
              <RiskSwatch level={l} className="h-full w-full" />
            </span>
          ))}
        </div>
        <dl className="num m-0 grid grid-cols-[1fr_auto] gap-y-1 text-sm">
          {miles.map((v, l) =>
            v > 0 ? (
              <div key={l} className="contents">
                <dt>{LEVEL_NAMES[l]}</dt>
                <dd className="m-0 text-right">{Math.round(v)} mi</dd>
              </div>
            ) : null,
          )}
          {route.score.unknown_mi > 0 && (
            <div className="contents text-ink-2">
              <dt>Beyond the forecast</dt>
              <dd className="m-0 text-right">{Math.round(route.score.unknown_mi)} mi</dd>
            </div>
          )}
        </dl>
      </div>
    </>
  );
}

export function HowToRead() {
  return (
    <div className="flex flex-col gap-2.5 text-sm leading-[21px]">
      <span className="text-[15px] font-bold">How to read this</span>
      <span>Each line is one way to drive this route. Going down means further along; flat means stopped for a break or rest.</span>
      <span>Where a line crosses colour, you'd meet that weather. The dashed line is the suggested later departure.</span>
      <span className="text-[13px] text-ink-2">Grey bands are night at the start. The thin blue line is the time on the slider.</span>
    </div>
  );
}
