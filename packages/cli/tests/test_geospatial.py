import numpy as np
import pytest

from ccel_cli.stac_client import build_stac_completeness_index, get_real_vcs1463_stac_scenes
from ccel_cli.sentinel2_clipper import (
    compute_scl_cloud_gap,
    compute_ndwi_tidal_inundation,
    compute_mean_ndvi,
    render_256x256_quicklook_png,
)
from ccel_cli.hansen_clipper import get_real_vcs1463_hansen_stats


def test_stac_completeness_index_sorting_and_hash():
    raw = get_real_vcs1463_stac_scenes()
    rule = {"maxCloudCoverPct": 20.0, "maxTidalInundationPct": 35.0}
    idx = build_stac_completeness_index(raw, rule)

    assert "indexSha256" in idx
    assert len(idx["indexSha256"]) == 64
    payload = idx["payload"]
    assert payload["totalScenesInCensus"] == len(raw)
    # Check deterministic sorting by datetime
    dts = [s["datetime"] for s in payload["scenes"]]
    assert dts == sorted(dts)


def test_scl_cloud_gap_calculation():
    # 100 pixels: 10 pixels of cloud (class 8), 10 pixels of shadow (class 3), 80 pixels vegetation (class 4)
    scl = np.array([8]*10 + [3]*10 + [4]*80)
    gap = compute_scl_cloud_gap(scl)
    assert gap == 20.0


def test_ndwi_tidal_inundation_calculation():
    # Green high, NIR low -> water (NDWI > 0.20)
    green = np.array([1200]*50 + [500]*50)
    nir = np.array([400]*50 + [3000]*50)
    scl = np.array([4]*100)

    inundation = compute_ndwi_tidal_inundation(green, nir, scl, ndwi_threshold=0.20)
    assert inundation == 50.0


def test_mean_ndvi_calculation():
    # Red 500, NIR 3000 -> NDVI = 2500/3500 = ~0.7143
    red = np.array([500]*100)
    nir = np.array([3000]*100)
    scl = np.array([4]*100)

    ndvi = compute_mean_ndvi(red, nir, scl)
    assert round(ndvi, 2) == 0.71


def test_hansen_real_stats_range_provenance():
    stats = get_real_vcs1463_hansen_stats()
    assert stats["hansenVersion"] == "GFC-2025-v1.13"
    assert stats["tile"] == "30N_080E"
    assert "httpRangeSpec" in stats
    assert "rawRangeSha256" in stats
    assert len(stats["rawRangeSha256"]) == 64
    assert stats["totalAoIPixels"] > 0
    assert "lossPixelsByYear" in stats
    assert len(stats["lossPixelsByYear"]) == 24


def test_quicklook_png_dimensions_and_size(tmp_path):
    cache_path = str(tmp_path / "test_thumb.jpg")
    png_bytes = render_256x256_quicklook_png(
        "https://sentinel-cogs.s3.us-west-2.amazonaws.com/sentinel-s2-l2a-cogs/45/Q/YE/2023/12/S2A_45QYE_20231230_0_L2A/thumbnail.jpg",
        cache_path,
        is_cloudy=False,
    )
    assert len(png_bytes) > 5000
    from PIL import Image
    import io
    im = Image.open(io.BytesIO(png_bytes))
    assert im.size == (256, 256)
    assert im.format == "PNG"
