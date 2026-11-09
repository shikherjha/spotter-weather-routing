import type { PickingInfo } from "@deck.gl/core";
import { MapboxOverlay, type MapboxOverlayProps } from "@deck.gl/mapbox";
import { useCallback, useEffect, useMemo, useRef } from "react";
import MapGL, { Marker, Popup, useControl, type MapRef } from "react-map-gl/maplibre";

import type { Stop, Trip, WeighStation } from "../../api/types";
import { heatmapRisk } from "../../lib/heatmap";
import { LEVEL_NAMES, mainReading } from "../../lib/risk";
import { mileAt, pointAtMile, routeById, tripHours } from "../../lib/route";
import { troubleSpots, type Pin } from "../../lib/summary";
import { HOUR, when } from "../../lib/time";
import { useUi } from "../../state";
import { Shield } from "../ui";
import { CheckpointCard } from "./CheckpointCard";
import { heatLayer, positionLayer, routeLayers, type Dot } from "./layers";

const STYLE = {
  light: "https://tiles.openfreemap.org/styles/positron",
  dark: "https://tiles.openfreemap.org/styles/dark",
};
const US_VIEW = { longitude: -98.5, latitude: 39.5, zoom: 3.6 };
const SHIELD_AT = 0.42; // fraction along each route: by then alternatives have usually split apart
const MIN_VIEW_PX = 120; // padding never squeezes the visible map below this


const TIP_STYLE = {
  background: "var(--surface)",
  color: "var(--ink)",
  font: "13px/18px 'Public Sans', system-ui",
  padding: "8px 10px",
  borderRadius: "8px",
  boxShadow: "var(--shadow)",
};

// Place names come from OpenStreetMap and NWS; the tooltip is HTML, so escape them.
const esc = (s: string) => s.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

function tipHtml({ object, layer }: PickingInfo<unknown>): string | null {
  if (!object) return null;
  if (layer?.id === "checkpoints") {
    const { cp, routeId } = object as Dot;
    const where = cp.place ? ` near ${esc(cp.place)}` : "";
    const level = cp.level === null ? "No forecast yet" : `${LEVEL_NAMES[cp.level]} · ${mainReading(cp)}`;
    return `<strong>Route ${routeId}, mile ${Math.round(cp.mile)}${where}</strong><br/>${when(cp.eta, cp.tz)}<br/>${level}`;
  }
  if (layer?.id === "stops") {
    const st = object as Stop;
    const what = st.kind === "break" ? "30-min break" : "10-h rest";
    return `<strong>${what}${st.place ? ` at ${esc(st.place)}` : ""}</strong><br/>Mile ${Math.round(st.mile)} · ${when(st.arrive, st.tz)}`;
  }
  if (layer?.id === "weigh") {
    const w = object as WeighStation;
    return `<strong>${esc(w.name)}</strong><br/>Mile ${Math.round(w.mile)} · ${when(w.eta, w.tz)}`;
  }
  return null;
}

export interface Padding {
  top: number;
  bottom: number;
  left: number;
  right: number;
}

function DeckOverlay(props: MapboxOverlayProps) {
  const overlay = useControl<MapboxOverlay>(() => new MapboxOverlay(props));
  overlay.setProps(props);
  return null;
}

/** Shrink padding that wouldn't fit the map (short laptop screens), keeping its proportions. */
function fitPadding(p: Padding, el: HTMLElement): Padding {
  const sx = Math.min(1, Math.max(0, el.clientWidth - MIN_VIEW_PX) / (p.left + p.right));
  const sy = Math.min(1, Math.max(0, el.clientHeight - MIN_VIEW_PX) / (p.top + p.bottom));
  return { top: p.top * sy, bottom: p.bottom * sy, left: p.left * sx, right: p.right * sx };
}

function bounds(trip: Trip): [[number, number], [number, number]] {
  let [w, s, e, n] = [180, 90, -180, -90];
  for (const r of trip.routes)
    for (const [lon, lat] of r.path) {
      w = Math.min(w, lon);
      e = Math.max(e, lon);
      s = Math.min(s, lat);
      n = Math.max(n, lat);
    }
  return [
    [w, s],
    [e, n],
  ];
}

export function MapView({ trip, padding }: { trip: Trip | null; padding: Padding }) {
  const mapRef = useRef<MapRef>(null);
  const framedTrip = useRef<string | null>(null);
  const userMoved = useRef(false);

  const theme = useUi((s) => s.theme);
  const hour = useUi((s) => s.hour);
  const weatherOn = useUi((s) => s.weatherOn);
  const selected = useUi((s) => s.selected);
  const focus = useUi((s) => s.focus);
  const select = useUi((s) => s.select);
  const setFocus = useUi((s) => s.setFocus);
  const setHour = useUi((s) => s.setHour);
  const openPanel = useUi((s) => s.openPanel);

  const picked = trip ? routeById(trip, selected) : null;
  const pins = useMemo(() => (trip ? troubleSpots(trip) : []), [trip]);
  const cellIndex = useMemo(() => (trip ? trip.heatmap.cells.map((_, i) => i) : []), [trip]);

  // A new trip is framed to fit; after that, panel changes only shift the view, unless the user hasn't
  // moved the map, in which case it is re-fitted so the routes stay in view above the panel.
  const frame = useCallback(() => {
    const map = mapRef.current;
    if (!map || !trip) return;
    const pad = fitPadding(padding, map.getContainer());
    if (framedTrip.current === trip.id && userMoved.current) {
      map.easeTo({ padding: pad, duration: 400 });
      return;
    }
    framedTrip.current = trip.id;
    userMoved.current = false;
    map.fitBounds(bounds(trip), { padding: pad, duration: 600 });
  }, [trip, padding]);
  useEffect(frame, [frame]);

  const routeLayerList = useMemo(
    () =>
      trip && picked
        ? routeLayers(trip, picked, theme, {
            onSelect: select,
            onCheckpoint: (routeId, cp) => {
              select(routeId);
              setFocus({ routeId, cp });
            },
          })
        : [],
    [trip, picked, theme, select, setFocus],
  );

  const layers = useMemo(() => {
    if (!trip || !picked) return [];
    const [h0, h1] = tripHours(trip, picked);
    const onRoad = weatherOn && hour >= h0 && hour <= h1;
    const here = onRoad ? pointAtMile(picked, mileAt(picked, trip.heatmap.start + hour * HOUR)) : null;
    return [heatLayer(trip, heatmapRisk(trip.heatmap), cellIndex, hour, theme, weatherOn), ...routeLayerList, positionLayer(here, theme)];
  }, [trip, picked, cellIndex, hour, theme, weatherOn, routeLayerList]);

  const tooltip = (info: PickingInfo<unknown>) => {
    const html = tipHtml(info);
    return html ? { html, style: TIP_STYLE } : null;
  };

  // Marker clicks must not reach the map, or the route line under the marker takes the click.
  const onMarker = (fn: () => void) => (e: { originalEvent: MouseEvent }) => {
    e.originalEvent.stopPropagation();
    fn();
  };

  const openPin = (p: Pin) => {
    if (!trip) return;
    select(p.routeId);
    setFocus({ routeId: p.routeId, cp: p.cp });
    setHour(Math.max(0, Math.min(trip.heatmap.hours - 1, Math.round((p.cp.eta - trip.heatmap.start) / HOUR))));
  };

  return (
    <MapGL
      ref={mapRef}
      onLoad={frame}
      onMoveStart={(e) => {
        if ("originalEvent" in e && e.originalEvent) userMoved.current = true;
      }}
      initialViewState={US_VIEW}
      mapStyle={STYLE[theme]}
      style={{ width: "100%", height: "100%" }}
      attributionControl={{ compact: true }}
      dragRotate={false}
      touchPitch={false}
    >
      <DeckOverlay layers={layers} getTooltip={tooltip} pickingRadius={6} />

      {trip?.routes.map((r) => {
        const [lon, lat] = pointAtMile(r, r.distance_mi * SHIELD_AT);
        return (
          <Marker key={`shield-${r.id}`} longitude={lon} latitude={lat} anchor="center" onClick={onMarker(() => select(r.id))}>
            <button type="button" aria-label={`Select route ${r.id}`} className="grid place-items-center">
              <Shield id={r.id} on={r.id === picked?.id} size={24} outlined />
            </button>
          </Marker>
        );
      })}

      {pins.map((p) => (
        <Marker key={p.key} longitude={p.lon} latitude={p.lat} anchor="bottom" onClick={onMarker(() => openPin(p))}>
          <div className="flex flex-col items-center">
            <button
              type="button"
              className="flex h-11 items-center gap-2 whitespace-nowrap rounded-full border border-rule bg-surface px-3 text-sm text-ink shadow-float max-lg:h-8 max-lg:gap-1.5 max-lg:px-2.5 max-lg:text-[13px]"
            >
              <span aria-hidden="true" className={`size-3 rounded-full risk-${p.level}`} />
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
          offset={14}
          closeButton={false}
          closeOnClick={false}
          onClose={() => setFocus(null)}
          maxWidth="280px"
        >
          <CheckpointCard trip={trip} routeId={focus.routeId} cp={focus.cp} onClose={() => setFocus(null)} onStops={() => openPanel("stops")} />
        </Popup>
      )}
    </MapGL>
  );
}
