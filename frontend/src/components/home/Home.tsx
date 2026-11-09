// The search-first home: where to, your truck, recent trips, and what's happening on the roads now.
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { getAlerts } from "../../api/client";
import type { Place } from "../../api/types";
import { MAX_LOAD_LB, parseLoad } from "../../lib/load";
import { recentTrips, type RecentTrip } from "../../lib/recent";
import { saveTruck, savedTruck } from "../../lib/truck";
import { PlaceInput } from "../form/PlaceInput";
import { TruckPill, type TruckFields } from "../form/TruckPill";
import { ChevronIcon, ClockIcon } from "../icons";

export function WhereTo({ onPick, autoFocus = false }: { onPick: (p: Place) => void; autoFocus?: boolean }) {
  return (
    <PlaceInput label="Where to?" value={null} onChange={(p) => p && onPick(p)} placeholder="Where to?" search autoFocus={autoFocus} />
  );
}

/** The saved truck, edited in place; a valid change is remembered right away. */
export function TruckSetting() {
  const [fields, setFields] = useState<TruckFields>(() => {
    const t = savedTruck();
    return { load: String(t.load_lb), heightFt: t.height_ft, hazmat: t.hazmat };
  });
  return (
    <TruckPill
      value={fields}
      onChange={(f) => {
        setFields(f);
        const load = parseLoad(f.load);
        if (load > 0 && load <= MAX_LOAD_LB) saveTruck({ load_lb: load, height_ft: f.heightFt, hazmat: f.hazmat });
      }}
    />
  );
}

export function RecentTrips({ onOpen }: { onOpen: (r: RecentTrip) => void }) {
  const [recent] = useState(recentTrips);
  if (!recent.length) return null;
  return (
    <div className="flex flex-col">
      <span className="px-0.5 pb-1 text-xs font-semibold text-ink-2">Recent</span>
      <ul className="m-0 list-none p-0">
        {recent.map((r) => (
          <li key={r.id} className="border-t border-rule">
            <button type="button" onClick={() => onOpen(r)} className="flex min-h-12 w-full items-center gap-3 px-1 text-left max-lg:min-h-14">
              <ClockIcon />
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="truncate text-[15px] font-semibold">{r.title}</span>
                <span className="num truncate text-[13px] text-ink-2">{r.detail}</span>
              </span>
              <ChevronIcon />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function DemoLink({ onDemo, busy }: { onDemo: () => void; busy: boolean }) {
  return (
    <button type="button" onClick={onDemo} disabled={busy} className="min-h-11 self-start text-left text-sm font-semibold text-accent disabled:opacity-60">
      Or try Dallas → Denver in a simulated storm
    </button>
  );
}

/** "Live · 12 warnings and 42 advisories in the US right now". */
export function LiveLine() {
  const alerts = useQuery({ queryKey: ["alerts"], queryFn: getAlerts, staleTime: 60_000, refetchInterval: 120_000 });
  const features = alerts.data?.features;
  if (!features || alerts.data?.updated == null) return null;
  const warnings = features.filter((f) => f.properties.kind === "warning").length;
  const advisories = features.length - warnings;
  const count = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
  return (
    <p className="num m-0 flex items-center gap-2 text-[13px] text-ink-2">
      <span aria-hidden="true" className="size-2 shrink-0 rounded-full bg-[var(--risk-0)]" />
      <span>
        <strong className="text-ink">Live</strong> · {count(warnings, "warning", "warnings")} and{" "}
        {count(advisories, "advisory", "advisories")} in the US right now
      </span>
    </p>
  );
}
