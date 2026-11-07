import { useEffect, useRef } from "react";

import type { Route, Trip } from "../../api/types";
import { arrivalTz } from "../../lib/route";
import { duration, when } from "../../lib/time";
import { useUi, type Panel } from "../../state";
import { CloseIcon } from "../icons";
import { Shield } from "../ui";
import { HowToRead, Warnings, WhyRoute } from "./RouteFacts";
import { StopsTable } from "./StopsTable";
import { Timeline } from "./Timeline";

const TABS: [Exclude<Panel, null>, string][] = [
  ["stops", "Stops"],
  ["timeline", "Timeline"],
];

/** Everything about one route, behind a tap. On narrow screens it covers the page as a dialog. */
export function Details({ trip, route, modal }: { trip: Trip; route: Route; modal: boolean }) {
  const panel = useUi((s) => s.panel);
  const openPanel = useUi((s) => s.openPanel);
  const heading = useRef<HTMLHeadingElement>(null);

  // Move focus into the panel when it opens, so keyboard and screen-reader users land on it.
  useEffect(() => heading.current?.focus(), []);

  return (
    <section
      role={modal ? "dialog" : undefined}
      aria-modal={modal || undefined}
      aria-labelledby="details-title"
      onKeyDown={(e) => e.key === "Escape" && openPanel(null)}
      className="flex h-full flex-col bg-surface lg:rounded-t-2xl lg:shadow-float"
    >
      <div className="flex min-h-14 shrink-0 flex-wrap items-center gap-x-3 gap-y-1 border-b border-rule py-2 pr-2 pl-6 max-md:pl-4">
        <Shield id={route.id} on size={24} />
        <h2 id="details-title" ref={heading} tabIndex={-1} className="m-0 text-[17px] font-bold outline-none">
          Route {route.id}
        </h2>
        <span className="num text-sm text-ink-2">
          {Math.round(route.distance_mi)} mi · {duration(route.duration_s)} · arrive {when(route.arrival, arrivalTz(route))}
        </span>
        <div role="group" aria-label="View" className="flex gap-0.5 rounded-[10px] bg-tint p-[3px] md:ml-6">
          {TABS.map(([key, name]) => (
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
        <div className="min-w-0">{panel === "timeline" ? <Timeline trip={trip} route={route} /> : <StopsTable trip={trip} route={route} />}</div>
        {/* On one column the warnings and reasons come first: they are what the driver came for. */}
        <aside className="flex flex-col gap-5 border-rule p-6 max-md:order-first max-md:border-b md:border-l">
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
