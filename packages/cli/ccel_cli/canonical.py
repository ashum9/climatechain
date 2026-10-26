"""
RFC 8785 (JSON Canonicalization Scheme - JCS) & RFC 6962 Domain-Separated Merkle Tree

Implements deterministic cryptographic canonicalization and leaf-level domain separation:
- RFC 8785: Lexicographical UTF-16 code unit key sorting, IEEE 754 float representation, no whitespace.
- RFC 6962: 0x00 domain prefix for leaves, 0x01 domain prefix for internal nodes.
"""

import hashlib
import json
import math
from typing import Any, Dict, List, Tuple


def canonicalize_json_bytes(obj: Any) -> bytes:
    """
    Serializes a Python object to canonical JSON bytes per RFC 8785 (JCS).
    """
    return _canonicalize_value(obj).encode("utf-8")


def canonicalize_json_str(obj: Any) -> str:
    """
    Returns the RFC 8785 canonical JSON string.
    """
    return _canonicalize_value(obj)


def _canonicalize_value(val: Any) -> str:
    if val is None:
        return "null"
    elif isinstance(val, bool):
        return "true" if val else "false"
    elif isinstance(val, (int, float)):
        if isinstance(val, float):
            if math.isnan(val) or math.isinf(val):
                raise ValueError("NaN and Infinity are not supported in RFC 8785 JSON")
            if val == 0.0:
                return "0"
            # Format float shortest round-trippable
            s = f"{val:.16g}"
            # Ensure Python's representation matches ECMAScript number format
            if "e" in s:
                parts = s.split("e")
                exp = int(parts[1])
                s = f"{parts[0]}e{'+' if exp >= 0 else ''}{exp}"
            return s
        return str(val)
    elif isinstance(val, str):
        # JSON string escaping per RFC 8785 / ECMA-404
        return json.dumps(val, ensure_ascii=False, separators=(",", ":"))
    elif isinstance(val, (list, tuple)):
        items = [_canonicalize_value(item) for item in val]
        return "[" + ",".join(items) + "]"
    elif isinstance(val, dict):
        # RFC 8785: Object keys sorted lexicographically by UTF-16 code units
        def utf16_sort_key(k: str):
            return [ord(c) for c in k]

        sorted_keys = sorted(val.keys(), key=utf16_sort_key)
        items = [
            f'{json.dumps(k, ensure_ascii=False, separators=(",", ":"))}:{_canonicalize_value(val[k])}'
            for k in sorted_keys
        ]
        return "{" + ",".join(items) + "}"
    else:
        raise TypeError(f"Type {type(val)} is not JSON serializable")


def hash_leaf(leaf_id: str, payload: Any) -> bytes:
    """
    RFC 6962 domain-separated leaf hash:
    SHA256(0x00 || UTF8(leaf_id) || 0x00 || RFC8785(payload))
    """
    payload_bytes = canonicalize_json_bytes(payload) if not isinstance(payload, bytes) else payload
    h = hashlib.sha256()
    h.update(b"\x00")
    h.update(leaf_id.encode("utf-8"))
    h.update(b"\x00")
    h.update(payload_bytes)
    return h.digest()


def hash_node(left_hash: bytes, right_hash: bytes) -> bytes:
    """
    RFC 6962 domain-separated internal node hash:
    SHA256(0x01 || left_hash || right_hash)
    """
    h = hashlib.sha256()
    h.update(b"\x01")
    h.update(left_hash)
    h.update(right_hash)
    return h.digest()


class MerkleTree:
    """
    RFC 6962 Binary Merkle Tree with deterministic promotion of odd nodes.
    """

    def __init__(self, leaves: List[Tuple[str, Any]]):
        """
        leaves: List of (leaf_id, payload) tuples, sorted deterministically by leaf_id.
        """
        self.leaf_entries = sorted(leaves, key=lambda x: [ord(c) for c in x[0]])
        self.leaf_ids = [k for k, _ in self.leaf_entries]
        self.leaf_hashes = [hash_leaf(k, payload) for k, payload in self.leaf_entries]
        self.layers: List[List[bytes]] = [self.leaf_hashes]
        self._build_tree()

    def _build_tree(self):
        current = self.leaf_hashes
        while len(current) > 1:
            next_layer = []
            for i in range(0, len(current), 2):
                if i + 1 < len(current):
                    next_layer.append(hash_node(current[i], current[i + 1]))
                else:
                    # RFC 6962 Section 2.1.1: promote odd node
                    next_layer.append(current[i])
            self.layers.append(next_layer)
            current = next_layer

    @property
    def root(self) -> bytes:
        if not self.leaf_hashes:
            return hashlib.sha256(b"").digest()
        return self.layers[-1][0]

    @property
    def root_hex(self) -> str:
        return "0x" + self.root.hex()

    def get_leaf_hex(self, leaf_id: str) -> str:
        idx = self.leaf_ids.index(leaf_id)
        return "0x" + self.leaf_hashes[idx].hex()

    def get_proof(self, leaf_id: str) -> List[Dict[str, str]]:
        if leaf_id not in self.leaf_ids:
            raise KeyError(f"Leaf {leaf_id} not in Merkle tree")

        idx = self.leaf_ids.index(leaf_id)
        proof = []

        for layer in self.layers[:-1]:
            is_right = (idx % 2 == 1)
            sibling_idx = idx - 1 if is_right else idx + 1
            if sibling_idx < len(layer):
                proof.append({
                    "position": "left" if is_right else "right",
                    "hash": "0x" + layer[sibling_idx].hex()
                })
            idx = idx // 2

        return proof


def verify_merkle_proof(leaf_id: str, payload: Any, proof: List[Dict[str, str]], root_hex: str) -> bool:
    current = hash_leaf(leaf_id, payload)
    for p in proof:
        sibling = bytes.fromhex(p["hash"].replace("0x", ""))
        if p["position"] == "left":
            current = hash_node(sibling, current)
        else:
            current = hash_node(current, sibling)

    return ("0x" + current.hex().lower()) == root_hex.lower()


def compute_package_hash(commitment_dict: Dict[str, Any]) -> str:
    """
    Computes packageHash = 0x || sha256(RFC8785(commitment_dict)).
    """
    canon_bytes = canonicalize_json_bytes(commitment_dict)
    return "0x" + hashlib.sha256(canon_bytes).hexdigest()


def compute_report_hash(report_commitment: Dict[str, Any]) -> str:
    """
    Computes reportHash = 0x || sha256(RFC8785(report_commitment)).
    """
    canon_bytes = canonicalize_json_bytes(report_commitment)
    return "0x" + hashlib.sha256(canon_bytes).hexdigest()

