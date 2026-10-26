"""
AoI-level Scene Classification Layer (SCL) Evaluator for Sentinel-2 COGs.

Measures cloud, cloud-shadow, water, and usable area specifically inside the
project Area of Interest (AoI), rather than relying on whole-tile eo:cloud_cover.

SCL Classes (Copernicus Sentinel-2 Level-2A):
  0: NO_DATA
  1: SATURATED_OR_DEFECTIVE
  2: DARK_AREA_PIXELS
  3: CLOUD_SHADOWS
  4: VEGETATION
  5: NOT_VEGETATED
  6: WATER
  7: UNCLASSIFIED
  8: CLOUD_MEDIUM_PROBABILITY
  9: CLOUD_HIGH_PROBABILITY
  10: THIN_CIRRUS
  11: SNOW_ICE
"""

import io
import json
import os
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pyproj
import requests
import tifffile

from ccel_cli.config import SUNDARBANS_VCS1463_BBOX_WGS84

CACHE_AOI_METRICS_PATH = "data/cache/aoi_metrics_cache.json"


def get_aoi_utm_bounds(
    bbox_wgs84: List[float] = SUNDARBANS_VCS1463_BBOX_WGS84,
    utm_epsg: str = "EPSG:32645",
) -> Tuple[float, float, float, float]:
    """
    Transforms WGS84 bbox [min_lon, min_lat, max_lon, max_lat] to UTM coordinates.
    Returns (min_x, min_y, max_x, max_y).
    """
    transformer = pyproj.Transformer.from_crs("EPSG:4326", utm_epsg, always_xy=True)
    min_lon, min_lat, max_lon, max_lat = bbox_wgs84
    x1, y1 = transformer.transform(min_lon, min_lat)
    x2, y2 = transformer.transform(max_lon, max_lat)
    return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))


def evaluate_scene_aoi(
    scene_id: str,
    scl_url: str,
    tile_cloud_pct: Optional[float] = None,
    bbox_wgs84: List[float] = SUNDARBANS_VCS1463_BBOX_WGS84,
    timeout_sec: int = 20,
) -> Dict[str, Any]:
    """
    Evaluates SCL pixel breakdown over the specified project AoI bounds.
    """
    min_x, min_y, max_x, max_y = get_aoi_utm_bounds(bbox_wgs84)

    resp = requests.get(scl_url, timeout=timeout_sec)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code} fetching SCL COG from {scl_url}")

    with tifffile.TiffFile(io.BytesIO(resp.content)) as tif:
        page = tif.pages[0]
        tie_x = float(page.tags["ModelTiepointTag"].value[3])
        tie_y = float(page.tags["ModelTiepointTag"].value[4])
        scale_x = float(page.tags["ModelPixelScaleTag"].value[0])
        scale_y = float(page.tags["ModelPixelScaleTag"].value[1])

        # Raster bounds in UTM
        height, width = page.shape
        tile_min_x = tie_x
        tile_max_x = tie_x + width * scale_x
        tile_max_y = tie_y
        tile_min_y = tie_y - height * scale_y

        inter_min_x = max(min_x, tile_min_x)
        inter_max_x = min(max_x, tile_max_x)
        inter_min_y = max(min_y, tile_min_y)
        inter_max_y = min(max_y, tile_max_y)

        if inter_min_x >= inter_max_x or inter_min_y >= inter_max_y:
            return {
                "sceneId": scene_id,
                "aoiIntersects": False,
                "aoiValidPixels": 0,
                "aoiCloudCoverPct": None,
                "aoiUsablePct": None,
                "tileCloudCoverPct": tile_cloud_pct,
            }

        c1 = max(0, int((inter_min_x - tie_x) / scale_x))
        c2 = min(width, int((inter_max_x - tie_x) / scale_x))
        r1 = max(0, int((tie_y - inter_max_y) / scale_y))
        r2 = min(height, int((tie_y - inter_min_y) / scale_y))

        arr = page.asarray()
        aoi_slice = arr[r1:r2, c1:c2]

    valid = aoi_slice != 0
    total_valid = int(np.sum(valid))
    if total_valid == 0:
        return {
            "sceneId": scene_id,
            "aoiIntersects": True,
            "aoiValidPixels": 0,
            "aoiCloudCoverPct": None,
            "aoiUsablePct": None,
            "tileCloudCoverPct": tile_cloud_pct,
        }

    cloud_shadow_mask = np.isin(aoi_slice, [3, 8, 9, 10]) & valid
    water_mask = (aoi_slice == 6) & valid
    clear_land_mask = np.isin(aoi_slice, [4, 5]) & valid

    cloud_count = int(np.sum(cloud_shadow_mask))
    water_count = int(np.sum(water_mask))
    clear_land_count = int(np.sum(clear_land_mask))

    aoi_cloud_pct = round(float(cloud_count / total_valid * 100.0), 4)
    aoi_water_pct = round(float(water_count / total_valid * 100.0), 4)
    aoi_clear_land_pct = round(float(clear_land_count / total_valid * 100.0), 4)
    aoi_usable_pct = round(float((1.0 - cloud_count / total_valid) * 100.0), 4)

    divergence_pct = None
    if tile_cloud_pct is not None:
        divergence_pct = round(float(aoi_cloud_pct - tile_cloud_pct), 4)

    return {
        "sceneId": scene_id,
        "aoiIntersects": True,
        "sliceRows": [r1, r2],
        "sliceCols": [c1, c2],
        "aoiValidPixels": total_valid,
        "aoiCloudPixels": cloud_count,
        "aoiWaterPixels": water_count,
        "aoiClearLandPixels": clear_land_count,
        "aoiCloudCoverPct": aoi_cloud_pct,
        "aoiWaterPct": aoi_water_pct,
        "aoiClearLandPct": aoi_clear_land_pct,
        "aoiUsablePct": aoi_usable_pct,
        "tileCloudCoverPct": tile_cloud_pct,
        "divergencePct": divergence_pct,
    }


def load_or_compute_metrics_cache(
    census_acquisitions: List[Dict[str, Any]],
    cache_path: str = CACHE_AOI_METRICS_PATH,
    sample_limit: Optional[int] = None,
) -> Dict[str, Dict[str, Any]]:
    """
    Loads cached AoI metrics or evaluates scenes, saving results to cache.
    """
    cache: Dict[str, Dict[str, Any]] = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            cache = {}

    to_process = census_acquisitions
    if sample_limit is not None:
        to_process = census_acquisitions[:sample_limit]

    modified = False
    for acq in to_process:
        scene_id = acq.get("canonicalItemId")
        scl_url = acq.get("sclHref")
        if not scene_id or not scl_url:
            continue
        if scene_id in cache:
            continue

        try:
            metrics = evaluate_scene_aoi(
                scene_id,
                scl_url,
                tile_cloud_pct=acq.get("tileCloudCoverPct"),
            )
            cache[scene_id] = metrics
            modified = True
        except Exception as err:
            cache[scene_id] = {
                "sceneId": scene_id,
                "error": str(err),
            }
            modified = True

    if modified:
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2)

    return cache
