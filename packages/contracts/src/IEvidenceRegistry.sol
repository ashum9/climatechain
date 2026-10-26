// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.24;

/**
 * @title IEvidenceRegistry
 * @notice Interface for the ClimateChain Evidence Registry on Ethereum Sepolia.
 * @dev Enforces cryptographic evidence packaging, role-gated reviews, acyclic supersession,
 *      and permissionless watchdog dispute challenges with reviewer adjudication.
 */
interface IEvidenceRegistry {
    enum Decision {
        NONE,
        APPROVED,
        REJECTED,
        NEEDS_EVIDENCE
    }

    enum ReasonCode {
        NONE,
        ALL_CHECKS_PASSED,
        CLOUD_GAP_EXCEEDED,
        TIDAL_INUNDATION_HIGH,
        OUT_OF_MONITORING_WINDOW,
        BOUNDARY_MISMATCH,
        INCOMPLETE_SCENE_SELECTION,
        ARTIFACT_HASH_MISMATCH,
        SERIAL_OVERLAP_DETECTED,
        OPTICAL_SAR_DIVERGENCE,
        GEOFENCE_OUT_OF_BOUNDS
    }

    enum TimingStatus {
        NONE,
        PRE_REGISTERED,
        POST_HOC
    }

    struct SelectionRuleRecord {
        bytes32 ruleHash;
        bytes32 projectIdHash;
        uint64 windowStart;
        uint64 windowEnd;
        uint64 registeredAt;
        TimingStatus timingStatus;
        address registeredBy;
        string ruleURI;
    }

    struct PackageRecord {
        bytes32 packageHash;
        bytes32 merkleRoot;
        bytes32 prevHash;
        bytes32 supersededBy;
        address submitter;
        uint64 submittedAt;
        uint32 reviewCount;
        Decision latestDecision;
        string manifestURI;
    }

    struct ReviewRecord {
        bytes32 packageHash;
        address reviewer;
        Decision decision;
        ReasonCode reasonCode;
        bytes32 reportHash;
        uint64 reviewedAt;
        string reportURI;
    }

    struct DisputeRecord {
        uint256 challengeId;
        bytes32 packageHash;
        address challenger;
        ReasonCode violatedReasonCode;
        bytes32 counterReportHash;
        string evidenceURI;
        uint64 challengedAt;
        bool resolved;
        bool upheld;
        address resolvedBy;
        uint64 resolvedAt;
    }

    // --- Events ---
    event ReviewerRoleUpdated(address indexed reviewer, bool indexed granted, address indexed updatedBy);
    event PackageSubmitted(bytes32 indexed packageHash, bytes32 indexed merkleRoot, address indexed submitter, string manifestURI, uint64 timestamp);
    event DuplicateSubmissionIgnored(bytes32 indexed packageHash, address indexed caller, uint64 timestamp);
    event PackageReviewed(bytes32 indexed packageHash, address indexed reviewer, Decision decision, ReasonCode reasonCode, bytes32 indexed reportHash, string reportURI, uint64 timestamp);
    event PackageSuperseded(bytes32 indexed prevHash, bytes32 indexed newHash, bytes32 newMerkleRoot, address indexed submitter, string newManifestURI, uint64 timestamp);
    event PackageChallenged(bytes32 indexed packageHash, uint256 indexed challengeId, address indexed challenger, ReasonCode violatedReasonCode, bytes32 counterReportHash, string evidenceURI, uint64 timestamp);
    event ChallengeResolved(bytes32 indexed packageHash, uint256 indexed challengeId, bool indexed upheld, Decision updatedDecision, address resolvedBy, uint64 timestamp);
    event SelectionRuleRegistered(bytes32 indexed ruleHash, bytes32 indexed projectIdHash, TimingStatus indexed timingStatus, uint64 windowStart, uint64 windowEnd, address registeredBy, string ruleURI, uint64 timestamp);

    // --- Custom Errors ---
    error ZeroHashNotAllowed();
    error UnauthorizedOwner(address caller);
    error UnauthorizedReviewer(address caller);
    error UnauthorizedSupersede(address caller, address expectedSubmitter);
    error UnknownPackage(bytes32 packageHash);
    error PackageAlreadyExists(bytes32 packageHash);
    error PackageAlreadySuperseded(bytes32 prevHash, bytes32 existingSuccessor);
    error InvalidDecision();
    error InvalidChallengeReason();
    error ChallengeAlreadyResolved(bytes32 packageHash, uint256 challengeId);
    error ChallengeNotFound(bytes32 packageHash, uint256 challengeId);

    // --- Core Functions ---
    function submit(bytes32 packageHash, bytes32 merkleRoot, string calldata manifestURI) external;
    function review(bytes32 packageHash, Decision decision, ReasonCode reasonCode, bytes32 reportHash, string calldata reportURI) external;
    function supersede(bytes32 newHash, bytes32 prevHash, bytes32 newMerkleRoot, string calldata newManifestURI) external;
    function challengePackage(bytes32 packageHash, ReasonCode violatedReasonCode, bytes32 counterReportHash, string calldata evidenceURI) external returns (uint256 challengeId);
    function resolveChallenge(bytes32 packageHash, uint256 challengeId, bool uphold, Decision updatedDecision) external;
    function registerSelectionRule(bytes32 ruleHash, bytes32 projectIdHash, uint64 windowStart, uint64 windowEnd, string calldata ruleURI) external returns (TimingStatus timingStatus);

    // --- View Functions ---
    function getPackage(bytes32 packageHash) external view returns (PackageRecord memory);
    function getReviews(bytes32 packageHash) external view returns (ReviewRecord[] memory);
    function getDisputes(bytes32 packageHash) external view returns (DisputeRecord[] memory);
    function getLineageChain(bytes32 anyHashInChain) external view returns (PackageRecord[] memory);
    function getSelectionRule(bytes32 ruleHash) external view returns (SelectionRuleRecord memory);
    function isReviewer(address account) external view returns (bool);
}
