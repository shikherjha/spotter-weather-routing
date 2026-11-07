import { latLngToCell } from "h3-js";
import { useMemo } from "react";

import type { Route, Trip } from "../../api/types";
import { heatmapRisk } from "../../lib/heatmap";
import { RISK_HEX } from "../../lib/risk";
import { cityName, pointAtMile } from "../../lib/route";
import { HOUR, localHour, tick } from "../../lib/time";
import { useUi } from "../../state";

// Space-time chart: miles along the route (down) against clock time (across), with the forecast behind.
const W = 1000;
const H = 400;
const X0 = 130;
const X1 = W - 16;
const Y0 = 14;
const Y1 = H - 34;
const ROWS = 140; // weather rows down the chart, so long routes don't draw thousands of cells
const MIN_ROW_MI = 5;
const TICK_EVERY_H = 6;

export function Timeline({ trip, route }: { trip: Trip; route: Route }) {
  const theme = useUi((s) => s.theme);
  const hour = useUi((s) => s.hour);
  const { start, hours } = trip.heatmap;
  const span = hours - 1;
  const cellW = (X1 - X0) / span;
  const x = (t: number) => X0 + ((t - start) / HOUR) * cellW;
  const y = (mi: number) => Y0 + (mi / route.distance_mi) * (Y1 - Y0);

  // Everything except the slider cursor depends only on the trip, route and theme.
  const chart = useMemo(() => {
    const risk = heatmapRisk(trip.heatmap);
    const index = new Map(trip.heatmap.cells.map((c, i) => [c, i]));
    const palette = RISK_HEX[theme];
    const step = Math.max(MIN_ROW_MI, route.distance_mi / ROWS);
    const rowH = (step / route.distance_mi) * (Y1 - Y0) + 0.3;
    const cells = [];
    for (let mi = 0; mi < route.distance_mi; mi += step) {
      const [lon, lat] = pointAtMile(route, mi + step / 2);
      const i = index.get(latLngToCell(lat, lon, trip.heatmap.resolution));
      if (i === undefined) continue;
      for (let h = 0; h < span; h++) {
        const level = risk[i * hours + h];
        if (level === 0 || level === 255) continue;
        cells.push(
          <rect
            key={`${mi}-${h}`}
            x={X0 + h * cellW}
            y={Y0 + (mi / route.distance_mi) * (Y1 - Y0)}
            width={cellW + 0.3}
            height={rowH}
            fill={palette[level]}
            opacity={level === 1 ? 0.6 : 0.85}
          />,
        );
      }
    }

    const nights = Array.from({ length: span }, (_, h) => h).filter((h) => {
      const lh = localHour(start + h * HOUR, trip.origin_tz);
      return lh >= 18 || lh < 6;
    });

    const drive = (offsetS: number) =>
      [
        ...route.checkpoints.map((c) => [c.eta + offsetS, c.mile] as const),
        ...route.stops.flatMap((s) => [[s.arrive + offsetS, s.mile] as const, [s.depart + offsetS, s.mile] as const]),
      ]
        .sort((a, b) => a[0] - b[0])
        .filter(([t]) => t <= start + span * HOUR)
        .map(([t, mi], i) => `${i ? "L" : "M"}${(X0 + ((t - start) / HOUR) * cellW).toFixed(1)},${(Y0 + (mi / route.distance_mi) * (Y1 - Y0)).toFixed(1)}`)
        .join(" ");

    const best = trip.departure_advice.best_offset_h;
    const bestOption = trip.departure_advice.options.find((o) => o.offset_h === best);
    return {
      cells,
      nights,
      now: drive(0),
      later: best > 0 && bestOption?.route_id === route.id ? drive(best * HOUR) : null,
    };
  }, [trip, route, theme, span, hours, start, cellW]);

  const marks = [
    { mi: 0, label: cityName(trip.origin.label) },
    ...route.stops.map((s) => ({ mi: s.mile, label: s.kind === "break" ? "Break" : "Rest" })),
    { mi: route.distance_mi, label: cityName(trip.destination.label) },
  ];
  const ticks = Array.from({ length: Math.floor(span / TICK_EVERY_H) + 1 }, (_, i) => i * TICK_EVERY_H);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-label={`Route ${route.id}: miles against time with the forecast weather`}>
      {chart.nights.map((h) => (
        <rect key={h} x={X0 + h * cellW} y={Y0} width={cellW + 0.3} height={Y1 - Y0} fill="var(--ink)" opacity={0.06} />
      ))}
      {chart.cells}
      {ticks.map((h) => (
        <g key={h}>
          <line x1={X0 + h * cellW} x2={X0 + h * cellW} y1={Y0} y2={Y1} stroke="var(--rule)" />
          <text x={X0 + h * cellW} y={Y1 + 18} fontSize="12" fill="var(--ink-2)" textAnchor={h === 0 ? "start" : h === span ? "end" : "middle"} className="num">
            {tick(start + h * HOUR, trip.origin_tz, h === 0 || localHour(start + h * HOUR, trip.origin_tz) < TICK_EVERY_H)}
          </text>
        </g>
      ))}
      <rect x={X0} y={Y0} width={X1 - X0} height={Y1 - Y0} fill="none" stroke="var(--rule)" />
      {marks.map((m) => (
        <text key={`${m.label}-${m.mi}`} x={X0 - 8} y={y(m.mi) + 4} fontSize="12" fill="var(--ink)" textAnchor="end">
          {m.label}
        </text>
      ))}
      {chart.later && <path d={chart.later} fill="none" stroke="var(--accent)" strokeWidth={2} strokeDasharray="5 3" />}
      <path d={chart.now} fill="none" stroke="var(--ink)" strokeWidth={2.2} strokeLinejoin="round" />
      <line x1={x(start + hour * HOUR)} x2={x(start + hour * HOUR)} y1={Y0 - 4} y2={Y1 + 4} stroke="var(--accent)" strokeWidth={1.5} />
    </svg>
  );
}
