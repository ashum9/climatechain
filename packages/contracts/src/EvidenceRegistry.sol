// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.24;

import {IEvidenceRegistry} from "./IEvidenceRegistry.sol";

/**
 * @title EvidenceRegistry
 * @notice Immutable evidence ledger for carbon project MRV verification on Ethereum Sepolia.
 * @dev Supports evidence submission, role-gated reviews, submitter-gated supersession DAGs,
 *      and permissionless watchdog challenges with reviewer resolution.
 */
contract EvidenceRegistry is IEvidenceRegistry {
    address public owner;
    mapping(address => bool) private _reviewers;
    mapping(bytes32 => PackageRecord) private _packages;
    mapping(bytes32 => ReviewRecord[]) private _reviews;
    mapping(bytes32 => DisputeRecord[]) private _disputes;
    mapping(bytes32 => SelectionRuleRecord) private _selectionRules;

    modifier onlyOwner() {
        if (msg.sender != owner) revert UnauthorizedOwner(msg.sender);
        _;
    }

    modifier onlyReviewer() {
        if (!_reviewers[msg.sender]) revert UnauthorizedReviewer(msg.sender);
        _;
    }

    constructor(address initialReviewer) {
        owner = msg.sender;
        if (initialReviewer != address(0)) {
            _reviewers[initialReviewer] = true;
            emit ReviewerRoleUpdated(initialReviewer, true, msg.sender);
        }
    }

    function setReviewer(address reviewer, bool granted) external onlyOwner {
        _reviewers[reviewer] = granted;
        emit ReviewerRoleUpdated(reviewer, granted, msg.sender);
    }

    function isReviewer(address account) external view override returns (bool) {
        return _reviewers[account];
    }

    function submit(
        bytes32 packageHash,
        bytes32 merkleRoot,
        string calldata manifestURI
    ) external override {
        if (packageHash == bytes32(0) || merkleRoot == bytes32(0)) {
            revert ZeroHashNotAllowed();
        }

        // Duplicate submission is a safe no-op with an event
        if (_packages[packageHash].submittedAt != 0) {
            emit DuplicateSubmissionIgnored(packageHash, msg.sender, uint64(block.timestamp));
            return;
        }

        _packages[packageHash] = PackageRecord({
            packageHash: packageHash,
            merkleRoot: merkleRoot,
            prevHash: bytes32(0),
            supersededBy: bytes32(0),
            submitter: msg.sender,
            submittedAt: uint64(block.timestamp),
            reviewCount: 0,
            latestDecision: Decision.NONE,
            manifestURI: manifestURI
        });

        emit PackageSubmitted(packageHash, merkleRoot, msg.sender, manifestURI, uint64(block.timestamp));
    }

    function review(
        bytes32 packageHash,
        Decision decision,
        ReasonCode reasonCode,
        bytes32 reportHash,
        string calldata reportURI
    ) external override onlyReviewer {
        if (_packages[packageHash].submittedAt == 0) {
            revert UnknownPackage(packageHash);
        }
        if (decision == Decision.NONE) {
            revert InvalidDecision();
        }
        if (reportHash == bytes32(0)) {
            revert ZeroHashNotAllowed();
        }

        ReviewRecord memory rec = ReviewRecord({
            packageHash: packageHash,
            reviewer: msg.sender,
            decision: decision,
            reasonCode: reasonCode,
            reportHash: reportHash,
            reviewedAt: uint64(block.timestamp),
            reportURI: reportURI
        });

        _reviews[packageHash].push(rec);
        _packages[packageHash].reviewCount += 1;
        _packages[packageHash].latestDecision = decision;

        emit PackageReviewed(
            packageHash,
            msg.sender,
            decision,
            reasonCode,
            reportHash,
            reportURI,
            uint64(block.timestamp)
        );
    }

    function supersede(
        bytes32 newHash,
        bytes32 prevHash,
        bytes32 newMerkleRoot,
        string calldata newManifestURI
    ) external override {
        if (newHash == bytes32(0) || prevHash == bytes32(0) || newMerkleRoot == bytes32(0)) {
            revert ZeroHashNotAllowed();
        }

        PackageRecord storage prevPkg = _packages[prevHash];
        if (prevPkg.submittedAt == 0) {
            revert UnknownPackage(prevHash);
        }
        if (msg.sender != prevPkg.submitter && msg.sender != owner) {
            revert UnauthorizedSupersede(msg.sender, prevPkg.submitter);
        }
        if (prevPkg.supersededBy != bytes32(0)) {
            revert PackageAlreadySuperseded(prevHash, prevPkg.supersededBy);
        }
        if (_packages[newHash].submittedAt != 0) {
            revert PackageAlreadyExists(newHash);
        }

        prevPkg.supersededBy = newHash;

        _packages[newHash] = PackageRecord({
            packageHash: newHash,
            merkleRoot: newMerkleRoot,
            prevHash: prevHash,
            supersededBy: bytes32(0),
            submitter: msg.sender,
            submittedAt: uint64(block.timestamp),
            reviewCount: 0,
            latestDecision: Decision.NONE,
            manifestURI: newManifestURI
        });

        emit PackageSubmitted(newHash, newMerkleRoot, msg.sender, newManifestURI, uint64(block.timestamp));
        emit PackageSuperseded(prevHash, newHash, newMerkleRoot, msg.sender, newManifestURI, uint64(block.timestamp));
    }

    /**
     * @notice Permissionless entrypoint for watchdogs to anchor an objective counter-report challenge.
     */
    function challengePackage(
        bytes32 packageHash,
        ReasonCode violatedReasonCode,
        bytes32 counterReportHash,
        string calldata evidenceURI
    ) external override returns (uint256 challengeId) {
        if (_packages[packageHash].submittedAt == 0) {
            revert UnknownPackage(packageHash);
        }
        if (counterReportHash == bytes32(0)) {
            revert ZeroHashNotAllowed();
        }
        if (violatedReasonCode == ReasonCode.NONE || violatedReasonCode == ReasonCode.ALL_CHECKS_PASSED) {
            revert InvalidChallengeReason();
        }

        challengeId = _disputes[packageHash].length;

        _disputes[packageHash].push(DisputeRecord({
            challengeId: challengeId,
            packageHash: packageHash,
            challenger: msg.sender,
            violatedReasonCode: violatedReasonCode,
            counterReportHash: counterReportHash,
            evidenceURI: evidenceURI,
            challengedAt: uint64(block.timestamp),
            resolved: false,
            upheld: false,
            resolvedBy: address(0),
            resolvedAt: 0
        }));

        emit PackageChallenged(
            packageHash,
            challengeId,
            msg.sender,
            violatedReasonCode,
            counterReportHash,
            evidenceURI,
            uint64(block.timestamp)
        );
    }

    /**
     * @notice Reviewer adjudication of an on-chain watchdog challenge.
     */
    function resolveChallenge(
        bytes32 packageHash,
        uint256 challengeId,
        bool uphold,
        Decision updatedDecision
    ) external override onlyReviewer {
        if (_packages[packageHash].submittedAt == 0) {
            revert UnknownPackage(packageHash);
        }
        if (challengeId >= _disputes[packageHash].length) {
            revert ChallengeNotFound(packageHash, challengeId);
        }

        DisputeRecord storage dispute = _disputes[packageHash][challengeId];
        if (dispute.resolved) {
            revert ChallengeAlreadyResolved(packageHash, challengeId);
        }

        dispute.resolved = true;
        dispute.upheld = uphold;
        dispute.resolvedBy = msg.sender;
        dispute.resolvedAt = uint64(block.timestamp);

        if (uphold) {
            if (updatedDecision == Decision.NONE) {
                updatedDecision = Decision.NEEDS_EVIDENCE;
            }
            _packages[packageHash].latestDecision = updatedDecision;

            // Automatically record an official ReviewRecord citing the counterReport
            _reviews[packageHash].push(ReviewRecord({
                packageHash: packageHash,
                reviewer: msg.sender,
                decision: updatedDecision,
                reasonCode: dispute.violatedReasonCode,
                reportHash: dispute.counterReportHash,
                reviewedAt: uint64(block.timestamp),
                reportURI: dispute.evidenceURI
            }));
            _packages[packageHash].reviewCount += 1;
        }

        emit ChallengeResolved(
            packageHash,
            challengeId,
            uphold,
            updatedDecision,
            msg.sender,
            uint64(block.timestamp)
        );
    }

    function getPackage(bytes32 packageHash) external view override returns (PackageRecord memory) {
        return _packages[packageHash];
    }

    function getReviews(bytes32 packageHash) external view override returns (ReviewRecord[] memory) {
        return _reviews[packageHash];
    }

    function getDisputes(bytes32 packageHash) external view override returns (DisputeRecord[] memory) {
        return _disputes[packageHash];
    }

    function getLineageChain(bytes32 anyHashInChain) external view override returns (PackageRecord[] memory) {
        if (_packages[anyHashInChain].submittedAt == 0) {
            return new PackageRecord[](0);
        }

        // 1. Walk backwards to root
        bytes32 current = anyHashInChain;
        uint256 depth = 0;
        while (_packages[current].prevHash != bytes32(0) && depth < 32) {
            current = _packages[current].prevHash;
            depth++;
        }

        bytes32 rootHash = current;

        // 2. Count total forward chain length from root
        uint256 total = 1;
        current = rootHash;
        while (_packages[current].supersededBy != bytes32(0) && total < 32) {
            current = _packages[current].supersededBy;
            total++;
        }

        // 3. Assemble chronological array
        PackageRecord[] memory chain = new PackageRecord[](total);
        current = rootHash;
        for (uint256 i = 0; i < total; i++) {
            chain[i] = _packages[current];
            current = _packages[current].supersededBy;
        }

        return chain;
    }

    function registerSelectionRule(
        bytes32 ruleHash,
        bytes32 projectIdHash,
        uint64 windowStart,
        uint64 windowEnd,
        string calldata ruleURI
    ) external override returns (TimingStatus timingStatus) {
        if (ruleHash == bytes32(0)) revert ZeroHashNotAllowed();

        TimingStatus status = block.timestamp < windowStart ? TimingStatus.PRE_REGISTERED : TimingStatus.POST_HOC;

        _selectionRules[ruleHash] = SelectionRuleRecord({
            ruleHash: ruleHash,
            projectIdHash: projectIdHash,
            windowStart: windowStart,
            windowEnd: windowEnd,
            registeredAt: uint64(block.timestamp),
            timingStatus: status,
            registeredBy: msg.sender,
            ruleURI: ruleURI
        });

        emit SelectionRuleRegistered(
            ruleHash,
            projectIdHash,
            status,
            windowStart,
            windowEnd,
            msg.sender,
            ruleURI,
            uint64(block.timestamp)
        );

        return status;
    }

    function getSelectionRule(bytes32 ruleHash) external view override returns (SelectionRuleRecord memory) {
        return _selectionRules[ruleHash];
    }
}
