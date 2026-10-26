"""
Merkle Leaf Differ Engine (v1 vs v2)
Compares two manifest commitments leaf-by-leaf:
Identifies invariant leaves (e.g. boundary KML 6c23a77...) and modified leaves (e.g. cloudy vs clear scene).
"""

from typing import Any, Dict, List
from ccel_cli.canonical import hash_leaf


def extract_merkle_leaves(commitment: Dict[str, Any]) -> Dict[str, Any]:
    leaves = {
        "00_boundary": commitment.get("boundary", {}),
        "01_monitoring_window": commitment.get("monitoringWindow", {}),
        "02_selection_rule": commitment.get("selectionRule", {}),
        "03_derived_metrics": commitment.get("derivedMetrics", {}),
    }

    for art in commitment.get("artifacts", []):
        art_id = art["artifactId"]
        leaves[f"04_artifact:{art_id}"] = art

    return leaves


def diff_manifest_commitments(
    old_commitment: Dict[str, Any],
    new_commitment: Dict[str, Any],
) -> Dict[str, Any]:
    old_leaves = extract_merkle_leaves(old_commitment)
    new_leaves = extract_merkle_leaves(new_commitment)

    all_keys = sorted(set(old_leaves.keys()) | set(new_leaves.keys()))
    diff_records = []

    for k in all_keys:
        in_old = k in old_leaves
        in_new = k in new_leaves

        if in_old and in_new:
            old_h = "0x" + hash_leaf(k, old_leaves[k]).hex()
            new_h = "0x" + hash_leaf(k, new_leaves[k]).hex()
            if old_h == new_h:
                status = "UNCHANGED"
            else:
                status = "MODIFIED"

            diff_records.append({
                "leafId": k,
                "status": status,
                "oldLeafHash": old_h,
                "newLeafHash": new_h,
                "oldPayload": old_leaves[k],
                "newPayload": new_leaves[k],
            })
        elif in_old:
            old_h = "0x" + hash_leaf(k, old_leaves[k]).hex()
            diff_records.append({
                "leafId": k,
                "status": "REMOVED",
                "oldLeafHash": old_h,
                "newLeafHash": None,
                "oldPayload": old_leaves[k],
                "newPayload": None,
            })
        else:
            new_h = "0x" + hash_leaf(k, new_leaves[k]).hex()
            diff_records.append({
                "leafId": k,
                "status": "ADDED",
                "oldLeafHash": None,
                "newLeafHash": new_h,
                "oldPayload": None,
                "newPayload": new_leaves[k],
            })

    return {
        "oldMerkleRoot": old_commitment.get("merkleRoot"),
        "newMerkleRoot": new_commitment.get("merkleRoot"),
        "totalLeaves": len(all_keys),
        "leafDiffs": diff_records,
    }
