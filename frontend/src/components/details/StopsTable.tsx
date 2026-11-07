import { useMemo, useState } from "react";

import type { Route, Trip } from "../../api/types";
import { itinerary } from "../../lib/itinerary";
import { LevelChip } from "../ui";

export function StopsTable({ trip, route }: { trip: Trip; route: Route }) {
  const [all, setAll] = useState(false);
  const rows = useMemo(() => itinerary(trip, route, all), [trip, route, all]);
  return (
    <div className="flex flex-col">
      <table className="num w-full border-collapse text-[13px]">
        <thead>
          <tr className="h-8 text-left text-ink-2">
            <th scope="col" className="w-14 pl-6 font-semibold max-md:pl-4">
              Mile
            </th>
            <th scope="col" className="px-2 font-semibold">
              Where
            </th>
            <th scope="col" className="px-2 font-semibold">
              You'd be there
            </th>
            <th scope="col" className="px-2 font-semibold max-md:hidden">
              Weather
            </th>
            <th scope="col" className="px-2 font-semibold">
              Risk
            </th>
            <th scope="col" className="pr-4 pl-2 font-semibold max-xl:hidden">
              Why
            </th>
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
              <td className="pr-4 pl-2 text-ink-2 max-xl:hidden">{r.reason}</td>
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
