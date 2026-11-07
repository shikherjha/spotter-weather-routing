import { latLngToCell } from "h3-js";
import { useMemo, useState } from "react";

import type { Route, Trip } from "../api/types";
import { RISK_HEX } from "../lib/risk";
import { duration, localHour, tick, when } from "../lib/time";
import { arrivalTz, itinerary, pointAtMile, shortArea, warningsOn } from "../lib/trip";
import { useUi, type Panel } from "../state";
import { AlertIcon, CloseIcon, LevelChip, Shield } from "./bits";

const HOUR = 3600;
const RENDER_RES = 6; // backend/engine/corridor.py RENDER_RES: the heatmap's cell size

export function Details({ trip, route }: { trip: Trip; route: Route }) {
  const { panel, openPanel } = useUi();
  const tabs: [Exclude<Panel, null>, string][] = [
    ["stops", "Stops"],
    ["timeline", "Timeline"],
  ];
  return (
    <section
      aria-label={`Route ${route.id} details`}
      className="flex h-full flex-col bg-surface md:rounded-t-2xl md:shadow-float"
    >
      <div className="flex min-h-14 shrink-0 flex-wrap items-center gap-x-3 gap-y-1 border-b border-rule py-2 pr-2 pl-6 max-md:pl-4">
        <Shield id={route.id} on size={24} />
        <span className="text-[17px] font-bold">Route {route.id}</span>
        <span className="num text-sm text-ink-2">
          {Math.round(route.distance_mi)} mi · {duration(route.duration_s)} · arrive {when(route.arrival, arrivalTz(route))}
        </span>
        <div role="group" aria-label="View" className="flex gap-0.5 rounded-[10px] bg-tint p-[3px] md:ml-6">
          {tabs.map(([key, name]) => (
            <button
              key={key}
              type="button"
              aria-pressed={panel === key}
              onClick={() => openPanel(key)}
              className={`h-9 rounded-[7px] px-3.5 text-sm font-semibold ${panel === key ? "bg-surface shadow-sm" : "text-ink-2"}`}
            >
              {name}
            </button>
          ))}
        </div>
        <div className="flex-1" />
        <button type="button" aria-label="Close details" onClick={() => openPanel(null)} className="grid size-11 place-items-center">
          <CloseIcon />
        </button>
      </div>
      <div className="grid min-h-0 flex-1 grid-cols-1 overflow-auto md:grid-cols-[minmax(0,1fr)_380px]">
        <div className="min-w-0">{panel === "timeline" ? <Timeline trip={trip} route={route} /> : <Stops trip={trip} route={route} />}</div>
        <aside className="flex flex-col gap-5 border-rule p-6 max-md:border-t md:border-l">
          {panel === "timeline" ? (
            <HowToRead />
          ) : (
            <>
              <Warnings trip={trip} route={route} />
              <WhyRoute trip={trip} route={route} />
            </>
          )}
        </aside>
      </div>
    </section>
  );
}

function Stops({ trip, route }: { trip: Trip; route: Route }) {
  const [all, setAll] = useState(false);
  const rows = useMemo(() => itinerary(trip, route, all), [trip, route, all]);
  return (
    <div className="flex flex-col">
      <table className="num w-full border-collapse text-[13px]">
        <thead>
          <tr className="h-8 text-left text-ink-2">
            <th scope="col" className="w-14 pl-6 font-semibold max-md:pl-4">Mile</th>
            <th scope="col" className="px-2 font-semibold">Where</th>
            <th scope="col" className="px-2 font-semibold">You'd be there</th>
            <th scope="col" className="px-2 font-semibold max-md:hidden">Weather</th>
            <th scope="col" className="px-2 font-semibold">Risk</th>
            <th scope="col" className="pr-4 pl-2 font-semibold max-lg:hidden">Why</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.key} className={`h-8 border-t border-rule ${r.kind === "stop" || r.kind === "zone" ? "bg-tint" : ""}`}>
              <td className="pl-6 text-ink-2 max-md:pl-4">{r.kind === "zone" ? "" : Math.round(r.mile)}</td>
              <td className={`px-2 ${r.kind === "point" ? "" : "font-semibold"} ${r.kind === "warning" ? "text-severe" : ""}`}>{r.place}</td>
              <td className="px-2">{r.time}</td>
              <td className="px-2 max-md:hidden">{r.weather}</td>
              <td className="px-2">{r.kind === "point" || r.kind === "end" ? <LevelChip level={r.level} /> : null}</td>
              <td className="pr-4 pl-2 text-ink-2 max-lg:hidden">{r.why}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <button type="button" onClick={() => setAll(!all)} className="h-11 self-start px-6 text-sm font-semibold text-accent max-md:px-4">
        {all ? "Show only the parts that matter" : `Show all ${route.checkpoints.length} checkpoints`}
      </button>
    </div>
  );
}

function Warnings({ trip, route }: { trip: Trip; route: Route }) {
  if (trip.warnings_status === "unavailable") {
    return <p className="m-0 text-sm text-ink-2">Official weather warnings are unavailable right now. Check weather.gov before you leave.</p>;
  }
  const found = warningsOn(trip, route.id);
  const setAside = warningsOn(trip, route.id, false);
  if (!found.length && !setAside.length) return null;
  return (
    <div className="flex flex-col gap-4 border-b border-rule pb-5">
      {found.map(({ warning: w, hit }) => (
        <article key={w.id} className="flex flex-col gap-1.5">
          <h3 className="m-0 flex items-center gap-2 text-[15px] font-bold">
            <AlertIcon /> {w.event}
          </h3>
          <p className="num m-0 text-sm leading-[21px]">
            {shortArea(w.area)}
            {w.ends && <>, until {when(w.ends, hit.tz)}</>}. You'd reach it {when(hit.enter, hit.tz)}, miles{" "}
            {Math.round(hit.from_mi)}–{Math.round(hit.to_mi)}.
          </p>
          <p className="m-0 text-sm leading-[21px]">{w.summary}</p>
          {w.road_closure && (
            <span className="self-start rounded bg-tint px-2 py-0.5 text-xs font-bold text-severe">Roads may close</span>
          )}
          <span className="text-xs text-ink-2">
            {w.source === "simulated" ? (
              "Simulated warning for the demo storm"
            ) : w.url ? (
              <a href={w.url} target="_blank" rel="noreferrer" className="text-ink-2 underline">
                National Weather Service
              </a>
            ) : (
              "National Weather Service"
            )}
            {w.triage === "jev" ? " · relevance checked by Jev" : ""}
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

function WhyRoute({ trip, route }: { trip: Trip; route: Route }) {
  const rec = route.recommended;
  const others = trip.routes.filter((r) => r.id !== route.id);
  return (
    <>
      <div className="flex flex-col gap-1.5">
        <span className="text-[15px] font-bold">{rec ? `Why Route ${route.id}` : `Why not Route ${route.id}`}</span>
        {rec ? (
          others.map((o) => (
            <span key={o.id} className="num text-sm leading-[21px]">
              {o.lost_on ? beatLine(o) : `Route ${o.id} is equally good.`}
            </span>
          ))
        ) : (
          <span className="num text-sm leading-[21px]">{route.lost_on ? lossLine(trip, route) : "It ties the recommended route."}</span>
        )}
        <span className="text-xs leading-[17px] text-ink-2">
          We rank by miles in No Travel, then Severe, then High weather, then average risk, then drive time.
        </span>
      </div>
      <Miles route={route} />
    </>
  );
}

const fmtValue = (criterion: string | null, v: number | null) =>
  v === null ? "—" : criterion === "duration_s" ? duration(v) : criterion === "avg_risk" ? v.toFixed(2) : `${Math.round(v)} mi`;

const PHRASE: Record<string, string> = {
  no_travel_mi: "of No Travel weather",
  severe_mi: "of Severe weather",
  high_mi: "of High weather",
  avg_risk: "average risk",
  duration_s: "of driving",
};

function beatLine(o: Route) {
  const l = o.lost_on!;
  return `Route ${o.id} has ${fmtValue(l.criterion, l.this_value)} ${PHRASE[l.criterion ?? ""] ?? l.label}; this one has ${fmtValue(l.criterion, l.winner_value)}.`;
}

function lossLine(trip: Trip, r: Route) {
  const l = r.lost_on!;
  return `It has ${fmtValue(l.criterion, l.this_value)} ${PHRASE[l.criterion ?? ""] ?? l.label}; Route ${trip.recommendation.route_id} has ${fmtValue(l.criterion, l.winner_value)}.`;
}

function Miles({ route }: { route: Route }) {
  const m = route.score.miles_by_level;
  const names = ["Low", "Moderate", "High", "Severe", "No Travel"];
  return (
    <div className="flex flex-col gap-2 border-t border-rule pt-5">
      <span className="text-[15px] font-bold">Miles by risk</span>
      <div className="flex h-2.5 overflow-hidden rounded-full" role="img" aria-label="Share of miles at each risk level">
        {m.map((v, l) => (
          <span key={l} className={`risk-${l}`} style={{ width: `${(v / route.distance_mi) * 100}%`, background: l < 4 ? `var(--risk-${l})` : undefined }} />
        ))}
      </div>
      <dl className="num m-0 grid grid-cols-[1fr_auto] gap-y-1 text-sm">
        {m.map((v, l) =>
          v > 0 ? (
            <div key={l} className="contents">
              <dt>{names[l]}</dt>
              <dd className="m-0 text-right">{Math.round(v)} mi</dd>
            </div>
          ) : null,
        )}
      </dl>
    </div>
  );
}

function HowToRead() {
  return (
    <div className="flex flex-col gap-2.5 text-sm leading-[21px]">
      <span className="text-[15px] font-bold">How to read this</span>
      <span>Each line is one way to drive this route. Going down means further along; flat means stopped for a break or rest.</span>
      <span>Where a line crosses colour, you'd meet that weather. The dashed line is the suggested later departure.</span>
      <span className="text-[13px] text-ink-2">Grey bands are night at the start. The thin blue line is the time on the slider.</span>
    </div>
  );
}

// Space-time chart: miles along the route (down) against clock time (across), with the forecast behind.
const W = 1000;
const H = 400;
const X0 = 130;
const X1 = W - 16;
const Y0 = 14;
const Y1 = H - 34;

function Timeline({ trip, route }: { trip: Trip; route: Route }) {
  const { theme, hour } = useUi();
  const { start, hours, cells, risk } = trip.heatmap;
  const span = hours - 1;
  const x = (t: number) => X0 + ((t - start) / HOUR / span) * (X1 - X0);
  const y = (mi: number) => Y0 + (mi / route.distance_mi) * (Y1 - Y0);

  const field = useMemo(() => {
    const bytes = Uint8Array.from(atob(risk), (c) => c.charCodeAt(0));
    const index = new Map(cells.map((c, i) => [c, i]));
    const step = Math.max(5, route.distance_mi / 140);
    const out: { mi: number; h: number; level: number }[] = [];
    for (let mi = 0; mi < route.distance_mi; mi += step) {
      const [lon, lat] = pointAtMile(route, mi + step / 2);
      const i = index.get(latLngToCell(lat, lon, RENDER_RES));
      if (i === undefined) continue;
      for (let h = 0; h < span; h++) {
        const l = bytes[i * hours + h];
        if (l > 0 && l !== 255) out.push({ mi, h, level: l });
      }
    }
    return { cells: out, step };
  }, [risk, cells, hours, span, route]);

  const line = (offsetS: number) =>
    [
      ...route.checkpoints.map((c) => [c.eta + offsetS, c.mile] as const),
      ...route.stops.flatMap((s) => [[s.arrive + offsetS, s.mile] as const, [s.depart + offsetS, s.mile] as const]),
    ]
      .sort((a, b) => a[0] - b[0])
      .filter(([t]) => t <= start + span * HOUR)
      .map(([t, mi], i) => `${i ? "L" : "M"}${x(t).toFixed(1)},${y(mi).toFixed(1)}`)
      .join(" ");

  const best = trip.departure_advice.best_offset_h;
  const bestOpt = trip.departure_advice.options.find((o) => o.offset_h === best);
  const showBest = best > 0 && bestOpt?.route_id === route.id;
  const pal = RISK_HEX[theme];
  const cellW = (X1 - X0) / span;
  const nights = Array.from({ length: span }, (_, h) => h).filter((h) => {
    const lh = localHour(start + h * HOUR, trip.origin_tz);
    return lh >= 18 || lh < 6;
  });
  const marks = [
    { mi: 0, label: trip.origin.label.split(",")[0] },
    ...route.stops.map((s) => ({ mi: s.mile, label: s.kind === "break" ? "Break" : "Rest" })),
    { mi: route.distance_mi, label: trip.destination.label.split(",")[0] },
  ];

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-label={`Route ${route.id}: miles against time with the forecast weather`}>
      {nights.map((h) => (
        <rect key={h} x={X0 + h * cellW} y={Y0} width={cellW + 0.3} height={Y1 - Y0} fill="var(--ink)" opacity={0.06} />
      ))}
      {field.cells.map((c) => (
        <rect
          key={`${c.mi}-${c.h}`}
          x={X0 + c.h * cellW}
          y={y(c.mi)}
          width={cellW + 0.3}
          height={(field.step / route.distance_mi) * (Y1 - Y0) + 0.3}
          fill={c.level === 4 ? pal[4] : pal[c.level]}
          opacity={c.level === 1 ? 0.6 : 0.85}
        />
      ))}
      {Array.from({ length: span / 6 + 1 }, (_, i) => i * 6).map((h) => (
        <g key={h}>
          <line x1={X0 + h * cellW} x2={X0 + h * cellW} y1={Y0} y2={Y1} stroke="var(--rule)" />
          <text
            x={X0 + h * cellW}
            y={Y1 + 18}
            fontSize="12"
            fill="var(--ink-2)"
            textAnchor={h === 0 ? "start" : h === span ? "end" : "middle"}
            className="num"
          >
            {tick(start + h * HOUR, trip.origin_tz, h === 0 || localHour(start + h * HOUR, trip.origin_tz) < 6)}
          </text>
        </g>
      ))}
      <rect x={X0} y={Y0} width={X1 - X0} height={Y1 - Y0} fill="none" stroke="var(--rule)" />
      {marks.map((m) => (
        <text key={`${m.label}-${m.mi}`} x={X0 - 8} y={y(m.mi) + 4} fontSize="12" fill="var(--ink)" textAnchor="end">
          {m.label}
        </text>
      ))}
      {showBest && <path d={line(best * HOUR)} fill="none" stroke="var(--accent)" strokeWidth={2} strokeDasharray="5 3" />}
      <path d={line(0)} fill="none" stroke="var(--ink)" strokeWidth={2.2} strokeLinejoin="round" />
      <line x1={X0 + hour * cellW} x2={X0 + hour * cellW} y1={Y0 - 4} y2={Y1 + 4} stroke="var(--accent)" strokeWidth={1.5} />
    </svg>
  );
}
