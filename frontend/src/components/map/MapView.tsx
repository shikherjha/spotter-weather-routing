import { H3HexagonLayer } from "@deck.gl/geo-layers";
import { PathLayer, ScatterplotLayer } from "@deck.gl/layers";
import { PathStyleExtension, type PathStyleExtensionProps } from "@deck.gl/extensions";
import { MapboxOverlay, type MapboxOverlayProps } from "@deck.gl/mapbox";
import type { PickingInfo } from "@deck.gl/core";
import { useCallback, useEffect, useMemo, useRef } from "react";
import MapGL, { Marker, Popup, useControl, type MapRef } from "react-map-gl/maplibre";

import type { Checkpoint, Route, Trip } from "../api/types";
import { HEAT_ALPHA, LEVEL_NAMES, RISK_RGB, THEME_RGB, hazard, reading, why, type RGB } from "../lib/risk";
import { duration, when } from "../lib/time";
import { mileAt, pointAtMile, slicePath, troubleSpots, tripHours, type Pin } from "../lib/trip";
import { useUi } from "../state";
import { LevelChip, Shield } from "./bits";

const STYLE = {
  light: "https://tiles.openfreemap.org/styles/positron",
  dark: "https://tiles.openfreemap.org/styles/dark",
};
const US_VIEW = { longitude: -98.5, latitude: 39.5, zoom: 3.6 };
const HOUR = 3600;

type RGBA = [number, number, number, number];
interface Line {
  path: [number, number][];
  color: RGBA;
  width: number;
  routeId: string;
  dashed?: boolean;
}
interface Dot {
  position: [number, number];
  cp: Checkpoint;
  routeId: string;
  selected: boolean;
}

function DeckOverlay(props: MapboxOverlayProps) {
  const overlay = useControl<MapboxOverlay>(() => new MapboxOverlay(props));
  overlay.setProps(props);
  return null;
}

const decode = (b64: string) => Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
const rgba = (c: RGB, a = 255): RGBA => [c[0], c[1], c[2], a];

export interface Padding {
  top: number;
  bottom: number;
  left: number;
  right: number;
}

export function MapView({ trip, padding }: { trip: Trip | null; padding: Padding }) {
  const mapRef = useRef<MapRef>(null);
  const { theme, hour, weatherOn, selected, focus, select, setFocus, setHour, openPanel } = useUi();
  const sel = trip?.routes.find((r) => r.id === selected) ?? trip?.routes[0] ?? null;

  const risk = useMemo(() => (trip ? decode(trip.heatmap.risk) : null), [trip]);
  const pins = useMemo(() => (trip ? troubleSpots(trip) : []), [trip]);

  // Frame every route whenever the trip or the space around the map changes (and once the map is ready).
  const frame = useCallback(() => {
    const map = mapRef.current;
    if (!map || !trip) return;
    let [w, s, e, n] = [180, 90, -180, -90];
    for (const r of trip.routes)
      for (const [lon, lat] of r.path) {
        w = Math.min(w, lon);
        e = Math.max(e, lon);
        s = Math.min(s, lat);
        n = Math.max(n, lat);
      }
    map.fitBounds([[w, s], [e, n]], { padding, duration: 600 });
  }, [trip, padding]);
  useEffect(frame, [frame]);

  const layers = useMemo(() => {
    if (!trip || !sel || !risk) return [];
    const pal = RISK_RGB[theme];
    const t = THEME_RGB[theme];
    const { cells, hours } = trip.heatmap;

    const ordered = [...trip.routes.filter((r) => r.id !== sel.id), sel];
    const lines: Line[] = [];
    for (const r of ordered) {
      const main = r.id === sel.id;
      const width = main ? 7 : 4.5;
      lines.push({ path: r.path, color: rgba(t.halo), width: width + 5, routeId: r.id });
      lines.push({ path: r.path, color: rgba(main ? t.accent : t.alt), width, routeId: r.id });
      for (const s of r.segments) {
        if (!s.level) continue;
        const path = slicePath(r, s.from_mi, s.to_mi);
        lines.push({ path, color: rgba(pal[s.level]), width, routeId: r.id });
        if (s.level === 4) lines.push({ path, color: rgba(t.halo, 200), width: 1.5, routeId: r.id, dashed: true });
      }
    }
    const dots: Dot[] = ordered.flatMap((r) =>
      r.checkpoints.map((cp) => ({ position: [cp.lon, cp.lat] as [number, number], cp, routeId: r.id, selected: r.id === sel.id })),
    );

    const t0 = trip.heatmap.start + hour * HOUR;
    const [h0, h1] = tripHours(trip, sel);
    const onTrip = weatherOn && hour >= h0 && hour <= h1;
    const here = onTrip ? pointAtMile(sel, mileAt(sel, t0)) : null;

    return [
      new H3HexagonLayer<number>({
        id: "heat",
        data: cells.map((_, i) => i),
        getHexagon: (i) => cells[i],
        getFillColor: (i) => {
          const l = risk[i * hours + hour];
          return l === 255 ? [0, 0, 0, 0] : rgba(pal[l], HEAT_ALPHA[l]);
        },
        stroked: false,
        extruded: false,
        visible: weatherOn,
        updateTriggers: { getFillColor: [hour, theme] },
      }),
      new PathLayer<Line>({
        id: "routes",
        data: lines.filter((l) => !l.dashed),
        getPath: (l) => l.path,
        getColor: (l) => l.color,
        getWidth: (l) => l.width,
        widthUnits: "pixels",
        jointRounded: true,
        capRounded: true,
        pickable: true,
        onClick: (info: PickingInfo<Line>) => info.object && select(info.object.routeId),
      }),
      new PathLayer<Line, PathStyleExtensionProps<Line>>({
        id: "no-travel-hatch",
        data: lines.filter((l) => l.dashed),
        getPath: (l) => l.path,
        getColor: (l) => l.color,
        getWidth: (l) => l.width,
        widthUnits: "pixels",
        getDashArray: [2, 2],
        extensions: [new PathStyleExtension({ dash: true })],
      }),
      new ScatterplotLayer<Dot>({
        id: "checkpoints",
        data: dots,
        getPosition: (d) => d.position,
        getRadius: (d) => (d.selected ? 2.4 : 1.6),
        radiusUnits: "pixels",
        getFillColor: rgba(t.halo, 235),
        pickable: true,
        onClick: (info: PickingInfo<Dot>) => {
          if (!info.object) return;
          select(info.object.routeId);
          setFocus({ routeId: info.object.routeId, cp: info.object.cp });
        },
      }),
      new ScatterplotLayer<Route["stops"][number]>({
        id: "stops",
        data: sel.stops,
        getPosition: (s) => [s.lon, s.lat],
        getRadius: 6,
        radiusUnits: "pixels",
        getFillColor: rgba(t.ink),
        getLineColor: rgba(t.halo),
        getLineWidth: 2,
        lineWidthUnits: "pixels",
        stroked: true,
      }),
      new ScatterplotLayer<[number, number]>({
        id: "ends",
        data: [sel.path[0], sel.path.at(-1)!],
        getPosition: (p) => p,
        getRadius: 6,
        radiusUnits: "pixels",
        getFillColor: rgba(t.halo),
        getLineColor: rgba(t.ink),
        getLineWidth: 3,
        lineWidthUnits: "pixels",
        stroked: true,
      }),
      new ScatterplotLayer<[number, number]>({
        id: "position",
        data: here ? [here] : [],
        getPosition: (p) => p,
        getRadius: 14,
        radiusUnits: "pixels",
        getFillColor: rgba(t.accent, 30),
        getLineColor: rgba(t.accent),
        getLineWidth: 2.5,
        lineWidthUnits: "pixels",
        stroked: true,
      }),
    ];
  }, [trip, sel, risk, theme, hour, weatherOn, select, setFocus]);

  const tooltip = ({ object, layer }: PickingInfo) => {
    if (!object || layer?.id !== "checkpoints") return null;
    const { cp, routeId } = object as Dot;
    return {
      html: `<strong>Route ${routeId} · mile ${Math.round(cp.mile)}</strong><br/>${when(cp.eta, cp.tz)}<br/>${cp.level === null ? "No forecast yet" : `${LEVEL_NAMES[cp.level]} · ${reading(cp)}`}`,
      style: {
        background: "var(--surface)",
        color: "var(--ink)",
        font: "13px/18px 'Public Sans', system-ui",
        padding: "8px 10px",
        borderRadius: "8px",
        boxShadow: "var(--shadow)",
      },
    };
  };

  // Marker clicks must not reach the map, or the route under the marker steals the click.
  const stop = (fn: () => void) => (e: { originalEvent: MouseEvent }) => {
    e.originalEvent.stopPropagation();
    fn();
  };

  const openPin = (p: Pin) => {
    select(p.routeId);
    setFocus({ routeId: p.routeId, cp: p.cp });
    if (trip) setHour(Math.max(0, Math.min(48, Math.round((p.cp.eta - trip.heatmap.start) / HOUR))));
  };

  return (
    <MapGL
      ref={mapRef}
      onLoad={frame}
      initialViewState={US_VIEW}
      mapStyle={STYLE[theme]}
      style={{ width: "100%", height: "100%" }}
      attributionControl={{ compact: true }}
      dragRotate={false}
      touchPitch={false}
    >
      <DeckOverlay layers={layers} getTooltip={tooltip} pickingRadius={6} />

      {trip?.routes.map((r) => {
        const [lon, lat] = pointAtMile(r, r.distance_mi * 0.42);
        return (
          <Marker key={`shield-${r.id}`} longitude={lon} latitude={lat} anchor="center" onClick={stop(() => select(r.id))}>
            <button type="button" aria-label={`Select route ${r.id}`} className="grid place-items-center">
              <Shield id={r.id} on={r.id === sel?.id} size={24} outlined />
            </button>
          </Marker>
        );
      })}

      {pins.map((p) => (
        <Marker key={p.key} longitude={p.lon} latitude={p.lat} anchor="bottom" onClick={stop(() => openPin(p))}>
          <div className="flex flex-col items-center">
            <button
              type="button"
              className="flex h-11 items-center gap-2 whitespace-nowrap rounded-full border border-rule bg-surface px-3 text-sm text-ink shadow-float max-md:h-8 max-md:gap-1.5 max-md:px-2.5 max-md:text-[13px]"
            >
              <span className={`size-3 rounded-full risk-${p.level}`} style={{ background: p.level < 4 ? `var(--risk-${p.level})` : undefined }} />
              <span className="font-bold">{p.title}</span>
              <span className="num text-ink-2">{p.detail}</span>
            </button>
            <span aria-hidden="true" className="h-3 w-0.5 bg-ink-2" />
          </div>
        </Marker>
      ))}

      {focus && trip && (
        <Popup
          longitude={focus.cp.lon}
          latitude={focus.cp.lat}
          anchor="left"
          offset={14}
          closeButton={false}
          closeOnClick={false}
          onClose={() => setFocus(null)}
          maxWidth="280px"
          focusAfterOpen={false}
        >
          <CheckpointCard
            trip={trip}
            routeId={focus.routeId}
            cp={focus.cp}
            onClose={() => setFocus(null)}
            onStops={() => openPanel("stops")}
          />
        </Popup>
      )}
    </MapGL>
  );
}

function CheckpointCard({
  trip,
  routeId,
  cp,
  onClose,
  onStops,
}: {
  trip: Trip;
  routeId: string;
  cp: Checkpoint;
  onClose: () => void;
  onStops: () => void;
}) {
  const reason = why(cp);
  return (
    <div className="flex w-64 flex-col gap-2 p-3.5 font-sans text-ink">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[15px] font-bold">{cp.level ? hazard(cp) : `Mile ${Math.round(cp.mile)}`}</span>
        <div className="flex items-center gap-1">
          <LevelChip level={cp.level} />
          <button type="button" aria-label="Close" onClick={onClose} className="grid size-8 place-items-center text-ink-2">
            <svg width="12" height="12" viewBox="0 0 16 16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 3 L13 13 M13 3 L3 13" />
            </svg>
          </button>
        </div>
      </div>
      <p className="num m-0 text-sm leading-5">
        Route {routeId}, mile {Math.round(cp.mile)}. You'd be here <strong>{when(cp.eta, cp.tz)}</strong>,{" "}
        {duration(cp.eta - trip.departure)} after you leave.
      </p>
      <p className="num m-0 text-sm leading-5">{reading(cp)}.</p>
      {reason && <p className="m-0 text-[13px] leading-5 text-ink-2">Why {cp.level !== null ? LEVEL_NAMES[cp.level] : ""}: {reason.toLowerCase()}.</p>}
      <button type="button" onClick={onStops} className="self-start text-sm font-semibold text-accent">
        All stops on Route {routeId}
      </button>
    </div>
  );
}
