# Security and Data Integrity Assessment Document

> **Compliance Requirement:** IEEE ClimateChain Organizer Specification (Deliverable #5)  
> **Target Audience:** IEEE Cybersecurity, Cryptography & Blockchain Judging Council  
> **Registry Contract:** [`0x8715ca679cb6b485b3c1e7d067c7e565dfd3347e`](https://sepolia.etherscan.io/address/0x8715ca679cb6b485b3c1e7d067c7e565dfd3347e)

---

## 1. Cryptographic Threat Model (STRIDE Assessment)

| Threat Category | Potential Attack Vector | System Vulnerability if Unmitigated | Architectural & Code Mitigations in CCEL |
| :--- | :--- | :--- | :--- |
| **Spoofing** | Unauthorized Reviewer impersonation | Malicious third party marks a fraudulent evidence package as `APPROVED`. | **Role-Gated Modifier (`onlyReviewer`):** Smart contract enforces `isReviewer[msg.sender] == true`. Reverts deterministically with custom error `UnauthorizedReviewer(caller)`. |
| **Tampering** | 1-byte data corruption or manipulation of derived stats | A project developer alters loss-pixel counts, cloud-gap numbers, or field photos in memory. | **RFC 6962 Domain-Separated Merkle Tree:** Every artifact is committed into an individual leaf. Any 1-byte alteration invalidates the leaf hash and produces a Merkle root mismatch against Sepolia. |
| **Repudiation / Withholding** | Auditor shopping & negative-review concealment | Project developer requests audits from 3 VVBs, conceals 2 rejected reviews, and only publishes the approved one. | **Append-Only On-Chain State:** All `NEEDS_EVIDENCE` and `REJECTED` reviews are mined on Sepolia against `packageHash`. Once submitted, a package cannot erase historical reviews. |
| **Information Disclosure / Licence** | Unlawful redistribution of third-party registry assets | Committing proprietary or copyright-restricted registry KML files to a public git repo. | **Zero-Redistribution Architecture:** Boundary KML is pinned strictly via SHA-256 (`6c23a77...`). The repo commits only statistical summaries. Browser verifies local files via WebCrypto. |
| **Denial of Service / Griefing** | Supersession hijacking & cycle creation | Attacker supersedes a legitimate package or creates an infinite loop (`v1 -> v2 -> v1`). | **Submitter Access Control & Acyclic DAG Invariants:** Only `packages[prevHash].submitter` can call `supersede`. Calling `supersede` with an already-existing `newHash` reverts with `PackageAlreadyExists`. |
| **Elevation of Privilege / Oracle Omission** | Scene cherry-picking (Selective Omission Attack) | Bundler includes 2 clear scenes and silently omits 10 cyclone-damaged scenes from the same monitoring window. | **STAC Completeness Index:** The builder queries AWS Earth Search STAC for all scenes in the window and commits `stac_completeness_index.json`. Check 5 verifies adherence to deterministic selection rules. |
| **Silent Collusion / VVB Capture** | VVB approves defective package despite obvious flaws | A corrupt auditor approves a cloudy or overlapping credit batch without public objection. | **Watchdog Dispute Protocol (`challengePackage`):** Permissionless on-chain dispute entrypoint allowing any independent observer to anchor a counter-report with bound reportHash on Sepolia. |

---

## 2. Cryptographic Hardening Details

### 2.1 Prevention of Second-Preimage Attacks
RFC 6962 enforces domain separation between leaf nodes and internal binary nodes:
* Leaves prepend a single `0x00` byte: `SHA256(0x00 || leafId || 0x00 || payload)`
* Internal nodes prepend a single `0x01` byte: `SHA256(0x01 || left || right)`
Because an internal node's preimage cannot begin with `0x00`, an attacker cannot construct an internal node that is accepted as a valid leaf payload.

### 2.2 Split Commitment vs. Provenance Envelope
To guarantee cross-machine determinism:
* The cryptographic Merkle root and `packageHash` cover **only the `commitment` section**.
* Mutable runtime metadata (`retrievedAtUtc`, builder runtime, mirror URLs) lives in `provenance`.
* Automated tests prove that two independent researchers building the package days apart compute identical hashes.

### 2.3 Strict Recomputation & Verification
The verification engine (both CLI and TypeScript Browser) independently reconstructs:
* The RFC 8785 canonical bytes for every artifact.
* The Merkle tree root and inclusion proofs.
* The full packageHash and check reportHash.
* Deep on-chain state queries against Sepolia RPC asserting 100% cryptographic parity.

---

## 3. Data Licensing and Attribution Audit

| Dataset / Asset | Origin / Source | License Terms | Compliance Posture in CCEL |
| :--- | :--- | :--- | :--- |
| **Verra VCS 1463 Boundary KML** | Verra Registry | Public download; redistribution license unresolved | **Zero redistribution.** Pinned strictly via SHA-256 constant `6c23a77...`. Tested via local WebCrypto file dropzone. |
| **Sentinel-2 L2A Imagery** | European Space Agency (ESA) / Copernicus | Copernicus Free, Full & Open License | Public AWS Open Data bucket (`s3://sentinel-s2-l2a`). Mandatory Copernicus attribution embedded in all metadata. |
| **Hansen Global Forest Change 2025** | University of Maryland / Google / USGS / NASA | Creative Commons Attribution 4.0 (CC BY 4.0) | Sourced from official GCS bucket. Mandatory CC BY 4.0 citation and scientific caveat embedded in all artifacts. Un-sampled strip decoding (4,005,982 pixels). |
| **Berkeley VROD Database** | UC Berkeley Carbon Trading Project | Creative Commons Attribution 4.0 (CC BY 4.0) | Documented and cited for registry serial cross-checks and interval-tree overlap detection. |

---

## 4. Demonstration Actors & Key Management Disclosure

In this testnet prototype deployment:
* The **Submitter**, **Independent Wildfire Auditor**, and **Lead Verification Reviewer** roles are demonstration wallets controlled by the team to execute the full multi-party dispute and supersession lifecycle on Ethereum Sepolia (`0xb1ce2e8ceb392ad3bf0e011d05689058dfa9210f`).
* All transactions and state transitions are cryptographically valid and mined on public testnet.
* In a commercial or production setting, these addresses correspond to independent third-party audit entities, decentralized oracles, and public watchdog organisations operating with multi-signature governance.
