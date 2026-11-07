"""Checkpoint placement and the miles each checkpoint stands for.

Checkpoints sit at 0, N, 2N, ... and always at the destination. Each one represents
the stretch from the midpoint with its previous neighbour to the midpoint with its
next (ends clipped to the route), so the represented miles sum exactly to the route
length and a short final gap gets a correspondingly small weight.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from engine.units import FloatArray

ALLOWED_INTERVALS_MI = (10, 25, 50)


@dataclass(frozen=True)
class Checkpoints:
    miles: FloatArray  # position along the route
    start_mi: FloatArray  # represented stretch [start_mi, end_mi]
    end_mi: FloatArray

    @property
    def weight_mi(self) -> FloatArray:
        return self.end_mi - self.start_mi

    def __len__(self) -> int:
        return int(self.miles.shape[0])


def place_checkpoints(length_mi: float, interval_mi: float) -> Checkpoints:
    if interval_mi <= 0:
        raise ValueError("interval_mi must be positive")
    if length_mi < 0:
        raise ValueError("length_mi must be non-negative")
    if length_mi == 0:
        z = np.zeros(1)
        return Checkpoints(z, z.copy(), z.copy())

    n_full = int(np.floor(length_mi / interval_mi + 1e-9))
    miles = np.arange(n_full + 1, dtype=np.float64) * interval_mi
    if length_mi - miles[-1] > 1e-6:
        miles = np.append(miles, length_mi)
    else:
        miles[-1] = length_mi  # absorb float drift so the last point is exactly the end

    mids = (miles[:-1] + miles[1:]) / 2
    start = np.concatenate(([0.0], mids))
    end = np.concatenate((mids, [length_mi]))
    return Checkpoints(miles, start, end)
