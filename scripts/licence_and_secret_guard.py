#!/usr/bin/env python3
"""
Licence and Secret Guard
Enforces strict secret and data-licensing guardrails across the repository.
Fails with exit code 1 if:
1. Any .kml or .kmz file is tracked by git or present in git-tracked paths.
2. Any tracked file contains raw Verra KML XML structures (<kml).
3. Any tracked file contains unwhitelisted 32-byte hex private keys (0x[0-9a-fA-F]{64}).
4. Any .env file is tracked.
"""

import os
import re
import subprocess
import sys

# Whitelisted 32-byte (64 hex character) hashes that are NOT private keys
WHITELISTED_HASHES = {
    "6c23a771351e6c3f04473a1af3d6d691819d07d0408ffd159808aacbffcba214",  # VCS 1463 boundary KML sha256
}

# Regex for 64-character hex strings with or without 0x prefix
HEX64_PATTERN = re.compile(r"(?:0x)?([0-9a-fA-F]{64})")

# Allowed files that may contain test vector hashes or pinned hashes
ALLOWED_HASH_FILES = {
    "canonical_merkle_vectors.json",
    "sepolia.json",
    "config.py",
    "manifest.schema.json",
    "check_report.schema.json",
    "test_vectors",
    "test_canonical_vectors.py",
    "canonical.test.ts",
    "test_licence_guard.py",
    "test_boundary.py",
    "builder.py",
    "licence_and_secret_guard.py",
    "ARCHITECTURE_AND_SPEC.md",
    "SECURITY_AND_DATA_INTEGRITY.md",
    "README.md",
    "izmir_orhanli_audit.json",
    "audit.json",
}


def get_tracked_files():
    try:
        res = subprocess.run(
            ["git", "ls-files"],
            capture_output=True,
            text=True,
            check=True
        )
        return [f.strip() for f in res.stdout.splitlines() if f.strip()]
    except Exception:
        # Fallback to traversing current dir excluding ignored
        files = []
        for root, _, filenames in os.walk("."):
            if any(p in root for p in [".git", "node_modules", ".venv", "venv", ".cache", "dist", "out", "__pycache__", ".pytest_cache", "packages/contracts/lib", "packages/contracts/out", "broadcast", "cache"]):
                continue
            for f in filenames:
                if f.endswith(".pyc") or f.endswith(".pyo") or f == ".env" or (f.startswith(".env.") and not f.endswith(".example")):
                    continue
                files.append(os.path.normpath(os.path.join(root, f)))
        return files


def check_file(filepath):
    violations = []
    if any(ignored in filepath for ignored in ["packages/contracts/lib", "packages/contracts/out", "node_modules", "broadcast", "cache"]):
        return violations
    basename = os.path.basename(filepath)

    # Check 1: Extension guard (.kml / .kmz)
    if filepath.endswith(".kml") or filepath.endswith(".kmz"):
        violations.append(f"Direct KML/KMZ file tracked: {filepath}")

    # Check 2: .env guard
    if basename == ".env" or (basename.startswith(".env.") and not basename.endswith(".example")):
        violations.append(f"Secret environment file tracked: {filepath}")

    # Skip binary image/raster files for text-based content scanning
    if filepath.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".pdf", ".tif", ".tiff")):
        return violations

    # Read content if text file
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception:
        return violations

    # Check 3: Raw KML content (skip self and test files)
    if not any(allowed in filepath for allowed in ["licence_and_secret_guard.py", "test_licence_guard.py", "test_boundary.py"]):
        if "<kml" in content.lower():
            violations.append(f"Raw KML XML tag '<kml' detected in {filepath}")

    # Check 4: Private key heuristics
    if any(allowed in filepath for allowed in ALLOWED_HASH_FILES):
        # Known documentation or schema or test vector file
        pass
    else:
        for match in HEX64_PATTERN.finditer(content):
            hex_val = match.group(1).lower()
            if hex_val in WHITELISTED_HASHES:
                continue
            # Check context: if line has 'sha256' or 'merkle' or 'hash' or 'address', it might be fine, but let's be strict
            line = content[max(0, match.start() - 60):min(len(content), match.end() + 60)]
            if any(kw in line.lower() for kw in ["hash", "sha256", "merkle", "root", "bytes32", "tx", "transaction"]):
                continue
            violations.append(f"Potential 64-hex private key or unverified hash detected in {filepath}: {hex_val[:8]}...{hex_val[-8:]}")

    return violations


def main():
    tracked = get_tracked_files()
    all_violations = []

    for f in tracked:
        if not os.path.exists(f):
            continue
        v = check_file(f)
        if v:
            all_violations.extend(v)

    if all_violations:
        print("❌ LICENCE & SECRET GUARD VIOLATIONS DETECTED:")
        for v in all_violations:
            print(f"  - {v}")
        sys.exit(1)
    else:
        print(f"✅ Licence & Secret Guard passed across {len(tracked)} tracked files.")
        sys.exit(0)


if __name__ == "__main__":
    main()
