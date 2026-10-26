import json
import os
import shutil
import tempfile
import pytest

from ccel_cli.builder import build_package
from ccel_cli.checks import evaluate_package
from ccel_cli.differ import diff_manifest_commitments


def test_builder_determinism():
    dir1 = tempfile.mkdtemp()
    dir2 = tempfile.mkdtemp()

    try:
        res1 = build_package("v2", dir1)
        res2 = build_package("v2", dir2)

        assert res1["packageHash"] == res2["packageHash"]
        assert res1["merkleRoot"] == res2["merkleRoot"]
        assert res1["reportHash"] == res2["reportHash"]

        # Ensure byte-for-byte identical manifest.json
        with open(os.path.join(dir1, "manifest.json"), "rb") as f1:
            b1 = f1.read()
        with open(os.path.join(dir2, "manifest.json"), "rb") as f2:
            b2 = f2.read()
        assert b1 == b2
    finally:
        shutil.rmtree(dir1)
        shutil.rmtree(dir2)


def test_v1_evaluation_catches_cloud_gap():
    temp_dir = tempfile.mkdtemp()
    try:
        res = build_package("v1", temp_dir)
        with open(os.path.join(temp_dir, "manifest.json"), "r") as f:
            manifest = json.load(f)

        eval_res = evaluate_package(manifest, temp_dir)
        report = eval_res["report"]["commitment"]

        assert report["overallRecommendedDecision"] == "NEEDS_EVIDENCE"
        assert report["recommendedReasonCode"] == "CLOUD_GAP_EXCEEDED"

        # Check 4 should fail
        check4 = next(c for c in report["checks"] if c["checkId"] == "CLOUD_AND_TIDAL_GAP")
        assert check4["status"] == "FAIL"
        assert check4["reasonCode"] == "CLOUD_GAP_EXCEEDED"
    finally:
        shutil.rmtree(temp_dir)


def test_v2_evaluation_passes_all_checks():
    temp_dir = tempfile.mkdtemp()
    try:
        res = build_package("v2", temp_dir)
        with open(os.path.join(temp_dir, "manifest.json"), "r") as f:
            manifest = json.load(f)

        eval_res = evaluate_package(manifest, temp_dir)
        report = eval_res["report"]["commitment"]

        assert report["overallRecommendedDecision"] == "APPROVED"
        assert report["recommendedReasonCode"] == "ALL_CHECKS_PASSED"

        # All 5 checks must pass
        for c in report["checks"]:
            assert c["status"] == "PASS", f"Check {c['checkId']} failed: {c['summary']}"
    finally:
        shutil.rmtree(temp_dir)


def test_tamper_detection_in_package():
    temp_dir = tempfile.mkdtemp()
    try:
        build_package("v2", temp_dir)
        with open(os.path.join(temp_dir, "manifest.json"), "r") as f:
            manifest = json.load(f)

        # Tamper with 1 byte in hansen_stats.json
        hansen_path = os.path.join(temp_dir, "hansen_stats.json")
        with open(hansen_path, "r") as f:
            hansen_json = json.load(f)
        hansen_json["totalAoIPixels"] += 1
        with open(hansen_path, "w") as f:
            json.dump(hansen_json, f)

        # Re-evaluate: must catch ARTIFACT_HASH_MISMATCH
        eval_res = evaluate_package(manifest, temp_dir)
        report = eval_res["report"]["commitment"]

        assert report["overallRecommendedDecision"] == "NEEDS_EVIDENCE"
        assert report["recommendedReasonCode"] == "ARTIFACT_HASH_MISMATCH"

        check1 = next(c for c in report["checks"] if c["checkId"] == "SOURCE_INTEGRITY")
        assert check1["status"] == "FAIL"
        assert check1["reasonCode"] == "ARTIFACT_HASH_MISMATCH"
    finally:
        shutil.rmtree(temp_dir)


def test_version_diff():
    dir1 = tempfile.mkdtemp()
    dir2 = tempfile.mkdtemp()
    try:
        build_package("v1", dir1)
        build_package("v2", dir2)

        with open(os.path.join(dir1, "manifest.json"), "r") as f:
            m1 = json.load(f)["commitment"]
        with open(os.path.join(dir2, "manifest.json"), "r") as f:
            m2 = json.load(f)["commitment"]

        diff = diff_manifest_commitments(m1, m2)
        diff_map = {d["leafId"]: d["status"] for d in diff["leafDiffs"]}

        assert diff_map["00_boundary"] == "UNCHANGED"
        assert diff_map["04_artifact:boundary-kml"] == "UNCHANGED"
        assert diff_map["04_artifact:hansen_stats.json"] == "UNCHANGED"
        assert diff_map["04_artifact:scene_metrics.json"] == "MODIFIED"
    finally:
        shutil.rmtree(dir1)
        shutil.rmtree(dir2)


def test_manifest_and_report_json_schema_validation():
    import jsonschema

    with open("schemas/manifest.schema.json") as f:
        manifest_schema = json.load(f)
    with open("schemas/check_report.schema.json") as f:
        report_schema = json.load(f)

    temp_dir = tempfile.mkdtemp()
    try:
        build_package("v2", temp_dir)
        with open(os.path.join(temp_dir, "manifest.json")) as f:
            manifest = json.load(f)
        with open(os.path.join(temp_dir, "check_report.json")) as f:
            report = json.load(f)

        # Validate against JSON Schemas
        jsonschema.validate(instance=manifest, schema=manifest_schema)
        jsonschema.validate(instance=report, schema=report_schema)
    finally:
        shutil.rmtree(temp_dir)

