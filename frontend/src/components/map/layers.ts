// deck.gl layers for the map. Route geometry is built once per trip, route and theme;
// the heatmap only recolours when the hour changes.
import { PathStyleExtension, type PathStyleExtensionProps } from "@deck.gl/extensions";
import type { PickingInfo } from "@deck.gl/core";
import { H3HexagonLayer } from "@deck.gl/geo-layers";
import { GeoJsonLayer, IconLayer, PathLayer, ScatterplotLayer } from "@deck.gl/layers";

import type { AlertAreas, Checkpoint, Pois, Poi, Route, Trip, WeighStation } from "../../api/types";
import { HEAT_ALPHA, RISK_RGB, THEME_RGB, type RGB, type Theme } from "../../lib/risk";
import { slicePath } from "../../lib/route";
import type { Layer } from "../../state";

type RGBA = [number, number, number, number];
const rgba = (c: RGB, a = 255): RGBA => [c[0], c[1], c[2], a];

const SELECTED_WIDTH = 7;
const OTHER_WIDTH = 4.5;
const HALO = 5;

interface Line {
  path: [number, number][];
  color: RGBA;
  width: number;
  routeId: string;
}

export interface Dot {
  position: [number, number];
  cp: Checkpoint;
  routeId: string;
  selected: boolean;
}

export interface RouteHandlers {
  onSelect: (routeId: string) => void;
  onCheckpoint: (routeId: string, cp: Checkpoint) => void;
}

/** Routes coloured by their own risk (picked route on top), checkpoints, weigh stations and the two ends. */
export function routeLayers(trip: Trip, picked: Route, theme: Theme, showWeigh: boolean, on: RouteHandlers) {
  const palette = RISK_RGB[theme];
  const ui = THEME_RGB[theme];
  const ordered = [...trip.routes.filter((r) => r.id !== picked.id), picked];
  const lines: Line[] = [];
  const hatches: Line[] = [];
  for (const r of ordered) {
    const width = r.id === picked.id ? SELECTED_WIDTH : OTHER_WIDTH;
    lines.push({ path: r.path, color: rgba(ui.halo), width: width + HALO, routeId: r.id });
    lines.push({ path: r.path, color: rgba(r.id === picked.id ? ui.accent : ui.alt), width, routeId: r.id });
    for (const s of r.segments) {
      if (!s.level) continue;
      const path = slicePath(r, s.from_mi, s.to_mi);
      lines.push({ path, color: rgba(palette[s.level]), width, routeId: r.id });
      if (s.level === 4) hatches.push({ path, color: rgba(ui.halo, 200), width: 1.5, routeId: r.id });
    }
  }
  const dots: Dot[] = ordered.flatMap((r) =>
    r.checkpoints.map((cp) => ({ position: [cp.lon, cp.lat], cp, routeId: r.id, selected: r.id === picked.id })),
  );

  return [
    new PathLayer<Line>({
      id: "routes",
      data: lines,
      getPath: (l) => l.path,
      getColor: (l) => l.color,
      getWidth: (l) => l.width,
      widthUnits: "pixels",
      jointRounded: true,
      capRounded: true,
      pickable: true,
      onClick: (info: PickingInfo<Line>) => info.object && on.onSelect(info.object.routeId),
    }),
    new PathLayer<Line, PathStyleExtensionProps<Line>>({
      id: "no-travel-hatch",
      data: hatches,
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
      getFillColor: rgba(ui.halo, 235),
      pickable: true,
      onClick: (info: PickingInfo<Dot>) => info.object && on.onCheckpoint(info.object.routeId, info.object.cp),
    }),
    new ScatterplotLayer<WeighStation>({
      id: "route-weigh",
      data: picked.weigh_stations,
      visible: showWeigh,
      getPosition: (w) => [w.lon, w.lat],
      getRadius: 4,
      radiusUnits: "pixels",
      getFillColor: rgba(ui.halo),
      getLineColor: rgba(ui.ink),
      getLineWidth: 2,
      lineWidthUnits: "pixels",
      stroked: true,
      pickable: true,
    }),
    new ScatterplotLayer<[number, number]>({
      id: "ends",
      data: [picked.path[0], picked.path[picked.path.length - 1]],
      getPosition: (p) => p,
      getRadius: 6,
      radiusUnits: "pixels",
      getFillColor: rgba(ui.halo),
      getLineColor: rgba(ui.ink),
      getLineWidth: 3,
      lineWidthUnits: "pixels",
      stroked: true,
    }),
  ];
}

/** Corridor risk at one hour. `cellIndex` must be stable per trip so hexagons are built only once. */
export function heatLayer(trip: Trip, risk: Uint8Array, cellIndex: number[], hour: number, theme: Theme, visible: boolean) {
  const { cells, hours } = trip.heatmap;
  const palette = RISK_RGB[theme];
  return new H3HexagonLayer<number>({
    id: "heat",
    data: cellIndex,
    getHexagon: (i) => cells[i],
    getFillColor: (i) => {
      const l = risk[i * hours + hour];
      return l === 255 ? [0, 0, 0, 0] : rgba(palette[l], HEAT_ALPHA[l]);
    },
    stroked: false,
    extruded: false,
    visible,
    updateTriggers: { getFillColor: [hour, theme] },
  });
}

/** Where the truck would be at the slider's time. */
export function positionLayer(at: [number, number] | null, theme: Theme) {
  const ui = THEME_RGB[theme];
  return new ScatterplotLayer<[number, number]>({
    id: "position",
    data: at ? [at] : [],
    getPosition: (p) => p,
    getRadius: 14,
    radiusUnits: "pixels",
    getFillColor: rgba(ui.accent, 30),
    getLineColor: rgba(ui.accent),
    getLineWidth: 2.5,
    lineWidthUnits: "pixels",
    stroked: true,
  });
}

const css = (c: RGB) => `rgb(${c[0]},${c[1]},${c[2]})`;
const square = (fill: RGB, stroke: RGB) =>
  `data:image/svg+xml;charset=utf-8,${encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"><rect x="3" y="3" width="18" height="18" rx="4" fill="${css(fill)}" stroke="${css(stroke)}" stroke-width="4"/></svg>`,
  )}`;

/** Truck stops (filled squares), rest areas (open squares) and weigh stations (open circles) across the US. */
export function placeLayers(pois: Pois | undefined, on: Record<Layer, boolean>, theme: Theme) {
  const ui = THEME_RGB[theme];
  const icon = (fill: RGB, stroke: RGB) => {
    const url = square(fill, stroke);
    return () => ({ url, id: url, width: 24, height: 24 });
  };
  // Sized in metres with pixel limits: small dots across a region, full-size markers when zoomed in.
  const shared = {
    getPosition: (p: Poi) => [p[1], p[0]] as [number, number],
    getSize: 3000,
    sizeUnits: "meters" as const,
    sizeMinPixels: 5,
    sizeMaxPixels: 12,
    pickable: true,
  };
  return [
    new IconLayer<Poi>({
      id: "rest-areas",
      data: pois?.rest_area ?? [],
      visible: on.restAreas,
      getIcon: icon(ui.halo, ui.ink),
      updateTriggers: { getIcon: theme },
      ...shared,
    }),
    new IconLayer<Poi>({
      id: "truck-stops",
      data: pois?.truck_stop ?? [],
      visible: on.truckStops,
      getIcon: icon(ui.ink, ui.halo),
      updateTriggers: { getIcon: theme },
      ...shared,
    }),
    new ScatterplotLayer<Poi>({
      id: "weigh-stations",
      data: pois?.weigh ?? [],
      visible: on.weigh,
      getPosition: shared.getPosition,
      getRadius: 1500,
      radiusUnits: "meters",
      radiusMinPixels: 2.5,
      radiusMaxPixels: 5,
      getFillColor: rgba(ui.halo),
      getLineColor: rgba(ui.ink),
      getLineWidth: 1.5,
      lineWidthUnits: "pixels",
      stroked: true,
      pickable: true,
    }),
  ];
}

type AlertFeature = AlertAreas["features"][number];

/** Active NWS warnings (stronger) and advisories or watches (lighter), US-wide. */
export function warningLayer(areas: AlertAreas | undefined, visible: boolean, theme: Theme) {
  const [warn, advise] = [RISK_RGB[theme][3], RISK_RGB[theme][2]];
  return new GeoJsonLayer<AlertFeature["properties"]>({
    id: "warnings",
    data: (areas?.features ?? []) as never,
    visible,
    filled: true,
    stroked: true,
    getFillColor: (f) => (f.properties.kind === "warning" ? rgba(warn, 56) : rgba(advise, 40)),
    getLineColor: (f) => (f.properties.kind === "warning" ? rgba(warn, 150) : rgba(advise, 140)),
    lineWidthUnits: "pixels",
    getLineWidth: 1,
    pickable: true,
    updateTriggers: { getFillColor: theme, getLineColor: theme },
  });
}
