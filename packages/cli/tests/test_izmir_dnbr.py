"""
Tests for the İzmir / Orhanlı 2025 wildfire dNBR burn-area and sensitivity evaluator.
"""

import json
import os
import numpy as np

from ccel_cli.izmir_dnbr import (
    IZMIR_ORHANLI_BBOX_WGS84,
    MGRS_TILE,
    NERO_PUBLISHED_ESTIMATES,
    PIXEL_AREA_HA,
    SECTOR_SPLIT_COL_OFFSET,
    WINDOW_C0,
    WINDOW_C1,
    WINDOW_R0,
    WINDOW_R1,
    _render_dnbr_png,
)


def test_study_area_and_nero_reference_constants():
    assert IZMIR_ORHANLI_BBOX_WGS84 == [26.78, 38.03, 27.08, 38.23]
    assert MGRS_TILE == "35SMC"
    assert (WINDOW_R1 - WINDOW_R0) == 1108
    assert (WINDOW_C1 - WINDOW_C0) == 1316
    assert PIXEL_AREA_HA == 0.04
    assert NERO_PUBLISHED_ESTIMATES["fireA_ha"] == 4277.7
    assert NERO_PUBLISHED_ESTIMATES["fireB_ha"] == 3541.9
    assert NERO_PUBLISHED_ESTIMATES["combined_ha"] == 7819.6


def test_dnbr_png_renderer(tmp_path):
    h, w = 100, 120
    dnbr = np.linspace(0.0, 0.8, h * w, dtype=np.float32).reshape(h, w)
    valid = np.ones((h, w), dtype=bool)
    out_file = tmp_path / "dnbr_test.png"
    sha = _render_dnbr_png(dnbr, valid, str(out_file), out_size=(120, 100))
    assert os.path.exists(out_file)
    assert len(sha) == 64


def test_cached_izmir_orhanli_audit_integrity():
    audit_path = "data/cache/izmir_orhanli_2025/izmir_orhanli_audit.json"
    if not os.path.exists(audit_path):
        return
    with open(audit_path, "r", encoding="utf-8") as f:
        audit = json.load(f)

    assert audit["caseId"] == "TURKIYE-IZMIR-ORHANLI-2025"
    kf = audit["keyFindings"]
    # Verify June 30 dNBR >= 0.20 brackets NERO's 7,819.6 ha closely (7,808.6 ha)
    assert abs(kf["june30At020ThresholdHa"] - 7808.6) < 1.0
    # Verify July 5 shows post-June-30 fire expansion (+1,917.6 ha at dNBR >= 0.20)
    assert kf["july05At020ThresholdHa"] > kf["june30At020ThresholdHa"] + 1500.0
    # Verify East + West sector sum equals total at every threshold
    for dt in ("2025-06-30", "2025-07-05"):
        for row in audit["comparisons"][dt]["thresholdSensitivity"]:
            assert abs((row["fireAEastHa"] + row["fireBWestHa"]) - row["calibratedTotalHa"]) <= 0.2
