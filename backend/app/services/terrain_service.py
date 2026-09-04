"""DEM-derived terrain features using Open-Meteo Elevation API.

For each zone centroid we sample a 3×3 grid at ~90 m spacing and derive:
- elevation_m  (mean of the 9 points; center point as fallback)
- slope_deg    (Horn's method on the 3×3 grid)
- aspect_deg   (Horn's method) → aspect_sin, aspect_cos
- curvature_1_m (second-derivative approximation: Laplacian / spacing²)

Open-Meteo elevation API returns integers in metres. All units are SI.
"""
from __future__ import annotations

import logging
import math
from typing import Dict, List, Tuple

import httpx

log = logging.getLogger("terrain_service")

_URL = "https://api.open-meteo.com/v1/elevation"
_SPACING_M = 300.0  # Open-Meteo elevation is ~90m native; 300m spacing gives a real gradient signal on mountain zones
_EARTH_R = 6371000.0


def _offsets(lat: float, lon: float, spacing_m: float) -> List[Tuple[float, float]]:
    """Return 9 (lat,lon) pairs on a 3×3 grid centred on (lat,lon).

    Order (row-major, top-left → bottom-right):
      [0]=NW [1]=N  [2]=NE
      [3]=W  [4]=C  [5]=E
      [6]=SW [7]=S  [8]=SE
    """
    dlat = (spacing_m / _EARTH_R) * (180.0 / math.pi)
    dlon = (spacing_m / (_EARTH_R * math.cos(math.radians(lat)))) * (180.0 / math.pi)
    grid = []
    for dy in (+1, 0, -1):  # north-first row
        for dx in (-1, 0, +1):  # west-first column
            grid.append((lat + dy * dlat, lon + dx * dlon))
    return grid


def _horn_slope_aspect(z: List[float], spacing_m: float) -> Tuple[float, float]:
    """Horn (1981) 3×3 slope & aspect.

    z indexed NW=0, N=1, NE=2, W=3, C=4, E=5, SW=6, S=7, SE=8.
    """
    dz_dx = ((z[2] + 2 * z[5] + z[8]) - (z[0] + 2 * z[3] + z[6])) / (8 * spacing_m)
    dz_dy = ((z[6] + 2 * z[7] + z[8]) - (z[0] + 2 * z[1] + z[2])) / (8 * spacing_m)
    slope = math.degrees(math.atan(math.hypot(dz_dx, dz_dy)))
    aspect_rad = math.atan2(dz_dy, -dz_dx)
    aspect_deg = (math.degrees(aspect_rad) + 360.0) % 360.0
    return slope, aspect_deg


def _curvature(z: List[float], spacing_m: float) -> float:
    """Discrete Laplacian ≈ profile+plan curvature (1/m).

    L = (N + S + E + W - 4*C) / spacing²
    """
    return (z[1] + z[7] + z[3] + z[5] - 4 * z[4]) / (spacing_m ** 2)


async def compute_dem_features(lat: float, lon: float, spacing_m: float = _SPACING_M) -> Dict[str, float]:
    coords = _offsets(lat, lon, spacing_m)
    lats = ",".join(f"{c[0]:.6f}" for c in coords)
    lons = ",".join(f"{c[1]:.6f}" for c in coords)
    async with httpx.AsyncClient(timeout=20) as c:
        r = await c.get(_URL, params={"latitude": lats, "longitude": lons})
        r.raise_for_status()
        z_list = r.json().get("elevation") or []
    if len(z_list) != 9 or any(v is None for v in z_list):
        raise RuntimeError(f"open-meteo elevation returned {len(z_list)} usable points")
    z = [float(v) for v in z_list]
    slope, aspect_deg = _horn_slope_aspect(z, spacing_m)
    curv = _curvature(z, spacing_m)
    return {
        "elevation_m": float(z[4]),  # centre point
        "slope_deg": round(slope, 3),
        "aspect_sin": round(math.sin(math.radians(aspect_deg)), 4),
        "aspect_cos": round(math.cos(math.radians(aspect_deg)), 4),
        "curvature_1_m": round(curv, 8),
    }
