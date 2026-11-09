"""H3 hexagon corridor around the routes, for the heatmap.

* Buffer in metres (local azimuthal-equidistant projection), never in degrees:
  a degree of longitude shrinks with latitude.
* Fill with H3 'overlap' mode so the corridor edge is fully covered.
* Render at res 6 (~3.7 km edge); fetch weather once per res-5 parent (~7x fewer
  API calls, still finer than the forecast models' effective resolution), then
  smooth parent values onto children with inverse-distance weighting.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import h3
import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import LineString
from shapely.ops import unary_union

from engine.geometry import METERS_PER_MILE, Polyline
from engine.units import FloatArray
from engine.weather import IntArray

RENDER_RES = 6
SAMPLE_RES = 5
SIGNATURE_RES = 7


def _aeqd(lat0: float, lon0: float) -> tuple[Transformer, Transformer]:
    crs = f"+proj=aeqd +lat_0={lat0} +lon_0={lon0} +units=m +datum=WGS84"
    fwd = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    inv = Transformer.from_crs(crs, "EPSG:4326", always_xy=True)
    return fwd, inv


@dataclass(frozen=True)
class Corridor:
    cells: list[str]  # render cells (res 6)
    centers: FloatArray  # (M, 2) lat, lon of render cells
    sample_cells: list[str]  # cells whose centres we fetch weather for (res 5)
    sample_centers: FloatArray  # (S, 2) lat, lon
    idw_index: IntArray  # (M, k) nearest sample cells per render cell
    idw_weight: FloatArray  # (M, k) weights, rows sum to 1

    def smooth(self, sample_values: FloatArray) -> FloatArray:
        """(S, ...) sample values -> (M, ...) render values."""
        w = self.idw_weight.reshape(self.idw_weight.shape + (1,) * (sample_values.ndim - 1))
        return np.sum(sample_values[self.idw_index] * w, axis=1)


def build_corridor(
    lines: Sequence[Polyline], half_width_mi: float, sample_res: int = SAMPLE_RES, k: int = 3
) -> Corridor:
    lat0 = float(np.mean(np.concatenate([ln.lats for ln in lines])))
    lon0 = float(np.mean(np.concatenate([ln.lons for ln in lines])))
    fwd, inv = _aeqd(lat0, lon0)

    buffers = []
    for ln in lines:
        projected = shapely.transform(LineString(np.column_stack([ln.lons, ln.lats])), fwd.transform, interleaved=False)
        simplified = shapely.simplify(projected, tolerance=250.0)
        buffers.append(simplified.buffer(half_width_mi * METERS_PER_MILE, quad_segs=4))
    area_lonlat = shapely.transform(unary_union(buffers), inv.transform, interleaved=False)

    cells = sorted(h3.h3shape_to_cells_experimental(h3.geo_to_h3shape(area_lonlat), RENDER_RES, contain="overlap"))
    centers = np.array([h3.cell_to_latlng(c) for c in cells])
    if sample_res == RENDER_RES:  # weather read at the heatmap's own cells: nothing to spread
        identity = np.arange(len(cells), dtype=np.intp)[:, None]
        return Corridor(cells, centers, cells, centers, identity, np.ones((len(cells), 1)))
    sample_cells = sorted({h3.cell_to_parent(c, sample_res) for c in cells})
    sample_centers = np.array([h3.cell_to_latlng(c) for c in sample_cells])
    idx, weight = idw_weights(centers, sample_centers, k=min(k, len(sample_cells)), lat0=lat0)
    return Corridor(cells, centers, sample_cells, sample_centers, idx, weight)


def idw_weights(
    targets: FloatArray, sources: FloatArray, k: int, lat0: float, power: float = 2.0, chunk: int = 2048
) -> tuple[IntArray, FloatArray]:
    """k-nearest inverse-distance weights on a local equirectangular plane (fine at corridor scale)."""
    scale = np.array([1.0, np.cos(np.radians(lat0))])
    src = sources * scale
    idx_out = np.empty((len(targets), k), dtype=np.intp)
    w_out = np.empty((len(targets), k))
    for start in range(0, len(targets), chunk):
        tgt = targets[start : start + chunk] * scale
        d2 = ((tgt[:, None, :] - src[None, :, :]) ** 2).sum(axis=2)
        nn = np.argpartition(d2, k - 1, axis=1)[:, :k] if k < src.shape[0] else np.tile(np.arange(k), (len(tgt), 1))
        dist = np.sqrt(np.take_along_axis(d2, nn, axis=1))
        w = 1.0 / np.maximum(dist, 1e-9) ** power
        exact = dist < 1e-9
        w = np.where(exact.any(axis=1, keepdims=True), exact.astype(float), w)
        idx_out[start : start + chunk] = nn
        w_out[start : start + chunk] = w / w.sum(axis=1, keepdims=True)
    return idx_out, w_out


def route_signature(line: Polyline, step_mi: float = 0.5) -> frozenset[str]:
    """Set of res-7 cells (~1.4 km) the route passes through, for overlap tests."""
    lats, lons = line.points_at(np.arange(0.0, line.length_mi + step_mi, step_mi))
    return frozenset(h3.latlng_to_cell(float(a), float(b), SIGNATURE_RES) for a, b in zip(lats, lons, strict=True))


def shared_fraction(candidate: frozenset[str], existing: frozenset[str]) -> float:
    """Share of the candidate's road that is also on an existing route (0..1)."""
    return len(candidate & existing) / len(candidate) if candidate else 1.0
