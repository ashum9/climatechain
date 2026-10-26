import pytest
from ccel_cli.vrod_checker import detect_serial_overlaps, parse_vcs_serial_block, get_vrod_audit_fixture
from ccel_cli.anomaly_radar import get_longitudinal_radar_fixture
from ccel_cli.photo_verifier import get_field_photos_fixture, verify_field_photo_record


def test_vrod_serial_parser():
    serial = "11452-319482101-319532100-VCS-VCU-263-VER-IN-14-1463-01012018-31122018-0"
    parsed = parse_vcs_serial_block(serial)
    assert parsed["startSerial"] == 319482101
    assert parsed["endSerial"] == 319532100
    assert parsed["unitCount"] == 50000
    assert parsed["projectId"] == "1463"


def test_vrod_overlap_detection():
    # v1 has an overlap of 2,500 units
    v1_audit = get_vrod_audit_fixture("v1")
    assert v1_audit["overlappingBatchesDetected"] == 1
    assert v1_audit["advisoryStatus"] == "SERIAL_OVERLAP_DETECTED"
    assert v1_audit["overlaps"][0]["overlappingUnits"] == 2500

    # v2 has clean disjoint intervals
    v2_audit = get_vrod_audit_fixture("v2")
    assert v2_audit["overlappingBatchesDetected"] == 0
    assert v2_audit["advisoryStatus"] == "ALL_CHECKS_PASSED"


def test_anomaly_radar_cyclone_amphan_and_divergence():
    # v1 has optical-SAR divergence due to cloud/water contamination
    v1_radar = get_longitudinal_radar_fixture("v1")
    eval_v1 = v1_radar["currentWindowEvaluation"]
    assert eval_v1["decision"] == "FAIL"
    assert eval_v1["opticalSarConsistencyStatus"] == "OPTICAL_SAR_DIVERGENCE"
    assert eval_v1["zScoreGrowth"] < -3.5

    # v2 shows verified dry-season additionality
    v2_radar = get_longitudinal_radar_fixture("v2")
    eval_v2 = v2_radar["currentWindowEvaluation"]
    assert eval_v2["decision"] == "PASS"
    assert eval_v2["opticalSarConsistencyStatus"] == "CONSISTENT_ADDITIVE_RECOVERY"
    assert eval_v2["zScoreGrowth"] > 0

    # Historical trajectory includes 2020 Cyclone Amphan event
    hist = v2_radar["historicalTrajectory"]
    amphan = next(h for h in hist if h["year"] == 2020)
    assert "Super Cyclone Amphan" in amphan["disturbanceEvent"]


def test_field_photo_polygon_geofence():
    # v1 has an off-parcel photo
    v1_photos = get_field_photos_fixture("v1")
    window = {"startDate": "2023-01-01", "endDate": "2023-12-31"}
    eval_v1 = [verify_field_photo_record(p, window) for p in v1_photos["photos"]]
    failing = [e for e in eval_v1 if e["status"] == "FAIL"]
    assert len(failing) == 1
    assert failing[0]["reasonCode"] == "GEOFENCE_OUT_OF_BOUNDS"

    # v2 has all photos inside restoration polygons
    v2_photos = get_field_photos_fixture("v2")
    eval_v2 = [verify_field_photo_record(p, window) for p in v2_photos["photos"]]
    assert all(e["status"] == "PASS" for e in eval_v2)
