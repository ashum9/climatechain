import { describe, it, expect } from "vitest";
import * as fs from "fs";
import * as path from "path";
import {
  canonicalizeJsonStr,
  MerkleTreeBrowser,
  verifyMerkleProof,
  computePackageHash,
} from "./canonical";

const vectorsPath = path.resolve(__dirname, "../../../../schemas/test_vectors/canonical_merkle_vectors.json");
const vectors = JSON.parse(fs.readFileSync(vectorsPath, "utf-8"));

describe("RFC 8785 (JCS) and RFC 6962 Cross-Language TypeScript Test", () => {
  it("Vector 1: should canonicalize float -0.0 to 0 and sort keys lexicographically", () => {
    const v1 = vectors.vector_1;
    const res = canonicalizeJsonStr(v1.input);
    expect(res).toBe(v1.canonical_json);
    expect(res).toBe('{"a":1,"b":0,"c":"hello"}');
  });

  it("Vector 2: should canonicalize nested objects and arrays", () => {
    const v2 = vectors.vector_2;
    const res = canonicalizeJsonStr(v2.input);
    expect(res).toBe(v2.canonical_json);
    expect(res).toBe('{"x":{"a":4675,"b":"Sundarbans"},"z":[3,2,1]}');
  });

  it("Vector 3: should match odd-leaf Merkle tree root and verify inclusion proof", async () => {
    const v3 = vectors.vector_3_odd_merkle;
    const entries = v3.leaves.map((l: any) => ({ leafId: l.id, payload: l.payload }));
    const tree = await MerkleTreeBrowser.create(entries);
    expect(tree.rootHex.toLowerCase()).toBe(v3.root_hex.toLowerCase());

    const valid = await verifyMerkleProof(
      "leaf_a",
      { val: 10 },
      v3.proof_leaf_a,
      v3.root_hex
    );
    expect(valid).toBe(true);
  });

  it("Vector 4: should match even-leaf Merkle tree root and verify inclusion proof", async () => {
    const v4 = vectors.vector_4_even_merkle;
    const entries = v4.leaves.map((l: any) => ({ leafId: l.id, payload: l.payload }));
    const tree = await MerkleTreeBrowser.create(entries);
    expect(tree.rootHex.toLowerCase()).toBe(v4.root_hex.toLowerCase());

    const valid = await verifyMerkleProof(
      "leaf_c",
      { val: 30 },
      v4.proof_leaf_c,
      v4.root_hex
    );
    expect(valid).toBe(true);
  });

  it("Vector 5: should compute identical packageHash for commitment", async () => {
    const v5 = vectors.vector_5_package_hash;
    const pkgHash = await computePackageHash(v5.commitment);
    expect(pkgHash.toLowerCase()).toBe(v5.package_hash.toLowerCase());
  });

  it("Provenance Invariant: changing retrievedAtUtc does not alter packageHash", async () => {
    const commitment = {
      projectId: "VCS-1463",
      merkleRoot: "0x1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
    };
    const hash1 = await computePackageHash(commitment);

    const manifestA = {
      commitment,
      provenance: { retrievedAtUtc: "2026-10-25T10:00:00Z" },
    };
    const manifestB = {
      commitment,
      provenance: { retrievedAtUtc: "2026-10-27T18:30:00Z" },
    };

    const hashA = await computePackageHash(manifestA.commitment);
    const hashB = await computePackageHash(manifestB.commitment);

    expect(hashA).toBe(hash1);
    expect(hashB).toBe(hash1);
    expect(hashA).toBe(hashB);
  });

  it("VROD Interval-Tree Overlap Detector in TypeScript", async () => {
    const { detectSerialOverlaps, parseVcsSerialBlock } = await import("../services/checkEngineBrowser");
    const serial = "11452-319482101-319532100-VCS-VCU-263-VER-IN-14-1463-01012018-31122018-0";
    const parsed = parseVcsSerialBlock(serial);
    expect(parsed.startSerial).toBe(319482101);
    expect(parsed.endSerial).toBe(319532100);
    expect(parsed.unitCount).toBe(50000);

    const overlappingRecords = [
      {
        claimId: "CLAIM-1",
        serialBlock: "11452-319482101-319532100-VCS-VCU-263-VER-IN-14-1463-01012018-31122018-0",
      },
      {
        claimId: "CLAIM-DUP",
        serialBlock: "11452-319490001-319492500-VCS-VCU-263-VER-IN-14-1463-01012018-31122018-0",
      },
    ];
    const overlaps = detectSerialOverlaps(overlappingRecords);
    expect(overlaps.length).toBe(1);
    expect(overlaps[0].overlappingUnits).toBe(2500);

    const cleanRecords = [
      {
        claimId: "CLAIM-1",
        serialBlock: "11452-319482101-319532100-VCS-VCU-263-VER-IN-14-1463-01012018-31122018-0",
      },
      {
        claimId: "CLAIM-2",
        serialBlock: "11452-319532101-319557100-VCS-VCU-263-VER-IN-14-1463-01012018-31122018-0",
      },
    ];
    expect(detectSerialOverlaps(cleanRecords).length).toBe(0);
  });
});
