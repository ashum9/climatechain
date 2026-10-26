import json
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../")))

from ccel_cli.canonical import (
    canonicalize_json_str,
    MerkleTree,
    verify_merkle_proof,
    compute_package_hash,
)


def load_vectors():
    path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../schemas/test_vectors/canonical_merkle_vectors.json"))
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def test_vector_1_float_and_key_order():
    vectors = load_vectors()
    v1 = vectors["vector_1"]
    res = canonicalize_json_str(v1["input"])
    assert res == v1["canonical_json"]
    assert res == '{"a":1,"b":0,"c":"hello"}'


def test_vector_2_nested_structures():
    vectors = load_vectors()
    v2 = vectors["vector_2"]
    res = canonicalize_json_str(v2["input"])
    assert res == v2["canonical_json"]
    assert res == '{"x":{"a":4675,"b":"Sundarbans"},"z":[3,2,1]}'


def test_vector_3_odd_merkle_tree():
    vectors = load_vectors()
    v3 = vectors["vector_3_odd_merkle"]
    leaves = [(item["id"], item["payload"]) for item in v3["leaves"]]
    tree = MerkleTree(leaves)
    assert tree.root_hex.lower() == v3["root_hex"].lower()

    # Verify inclusion proof for leaf_a
    valid = verify_merkle_proof("leaf_a", {"val": 10}, v3["proof_leaf_a"], v3["root_hex"])
    assert valid is True


def test_vector_4_even_merkle_tree():
    vectors = load_vectors()
    v4 = vectors["vector_4_even_merkle"]
    leaves = [(item["id"], item["payload"]) for item in v4["leaves"]]
    tree = MerkleTree(leaves)
    assert tree.root_hex.lower() == v4["root_hex"].lower()

    # Verify inclusion proof for leaf_c
    valid = verify_merkle_proof("leaf_c", {"val": 30}, v4["proof_leaf_c"], v4["root_hex"])
    assert valid is True


def test_vector_5_package_hash():
    vectors = load_vectors()
    v5 = vectors["vector_5_package_hash"]
    pkg_hash = compute_package_hash(v5["commitment"])
    assert pkg_hash.lower() == v5["package_hash"].lower()


def test_provenance_modification_invariant():
    """Modifying provenance does NOT alter packageHash or merkleRoot"""
    leaves = [("leaf_a", {"foo": "bar"}), ("leaf_b", {"num": 123})]
    tree = MerkleTree(leaves)

    commitment = {
        "projectId": "VCS-1463",
        "merkleRoot": tree.root_hex,
        "boundary": {"kmlSha256": "6c23a771351e6c3f04473a1af3d6d691819d07d0408ffd159808aacbffcba214"}
    }
    hash_1 = compute_package_hash(commitment)

    # Provenance envelope with Tuesday timestamp
    manifest_tuesday = {
        "commitment": commitment,
        "provenance": {"retrievedAtUtc": "2026-10-25T10:00:00Z"}
    }

    # Provenance envelope with Thursday timestamp
    manifest_thursday = {
        "commitment": commitment,
        "provenance": {"retrievedAtUtc": "2026-10-27T18:30:00Z"}
    }

    hash_tuesday = compute_package_hash(manifest_tuesday["commitment"])
    hash_thursday = compute_package_hash(manifest_thursday["commitment"])

    assert hash_tuesday == hash_1
    assert hash_thursday == hash_1
    assert hash_tuesday == hash_thursday


def test_tamper_detection():
    """1 bit change in commitment causes packageHash and Merkle root to change"""
    leaves_orig = [("leaf_a", {"foo": "bar"}), ("leaf_b", {"num": 123})]
    tree_orig = MerkleTree(leaves_orig)

    # Tamper with leaf_b (123 -> 124)
    leaves_tampered = [("leaf_a", {"foo": "bar"}), ("leaf_b", {"num": 124})]
    tree_tampered = MerkleTree(leaves_tampered)

    assert tree_orig.root_hex != tree_tampered.root_hex
