// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {IEvidenceRegistry} from "../src/IEvidenceRegistry.sol";
import {EvidenceRegistry} from "../src/EvidenceRegistry.sol";

contract EvidenceRegistryTest is Test {
    EvidenceRegistry public registry;

    address public owner = address(0xAA1);
    address public reviewer = address(0xBB2);
    address public submitter = address(0xCC3);
    address public stranger = address(0xDD4);

    bytes32 public v1Hash = 0x1e9a0c261c393c1080526f791863ffd1933b559c9f369df3df5ab55c59d84612;
    bytes32 public v1MerkleRoot = 0x2069290b7259abf1dd1216244201f89be1f00793c39983d6bc5dcee889e07f1b;
    bytes32 public v1ReportHash = 0xf79e573c1d82b8805ab1acdf5ef0b563b1ef26936330c434862586bdb59984b1;

    bytes32 public v2Hash = 0x37824f51332abd3ff1c885d8d755e997adc0d96b6c70feab8149acf34dcf17fa;
    bytes32 public v2MerkleRoot = 0x87b9db192e25ad0958e2dfea6af0c8a6c3490e1f50e9ff2c4bfba664d4c274ab;
    bytes32 public v2ReportHash = 0x225b958e5f699c63cdc5227d889d7969a911a33cefbc5ff0fa8cd8ff61e2accd;

    string public v1URI = "ipfs://QmTestV1Manifest";
    string public v2URI = "ipfs://QmTestV2Manifest";

    event PackageSubmitted(bytes32 indexed packageHash, bytes32 indexed merkleRoot, address indexed submitter, string manifestURI, uint64 timestamp);
    event DuplicateSubmissionIgnored(bytes32 indexed packageHash, address indexed caller, uint64 timestamp);
    event PackageReviewed(bytes32 indexed packageHash, address indexed reviewer, IEvidenceRegistry.Decision decision, IEvidenceRegistry.ReasonCode reasonCode, bytes32 indexed reportHash, string reportURI, uint64 timestamp);
    event PackageSuperseded(bytes32 indexed prevHash, bytes32 indexed newHash, bytes32 newMerkleRoot, address indexed submitter, string newManifestURI, uint64 timestamp);

    function setUp() public {
        vm.prank(owner);
        registry = new EvidenceRegistry(reviewer);
    }

    function test_InitialState() public view {
        assertEq(registry.owner(), owner);
        assertTrue(registry.isReviewer(reviewer));
        assertFalse(registry.isReviewer(stranger));
    }

    function test_SubmitPackage() public {
        vm.prank(submitter);
        vm.expectEmit(true, true, true, false);
        emit PackageSubmitted(v1Hash, v1MerkleRoot, submitter, v1URI, uint64(block.timestamp));

        registry.submit(v1Hash, v1MerkleRoot, v1URI);

        IEvidenceRegistry.PackageRecord memory pkg = registry.getPackage(v1Hash);
        assertEq(pkg.packageHash, v1Hash);
        assertEq(pkg.merkleRoot, v1MerkleRoot);
        assertEq(pkg.prevHash, bytes32(0));
        assertEq(pkg.supersededBy, bytes32(0));
        assertEq(pkg.submitter, submitter);
        assertEq(pkg.manifestURI, v1URI);
        assertEq(uint8(pkg.latestDecision), uint8(IEvidenceRegistry.Decision.NONE));
        assertEq(pkg.reviewCount, 0);
    }

    function test_DuplicateSubmitIsNoOp() public {
        vm.prank(submitter);
        registry.submit(v1Hash, v1MerkleRoot, v1URI);

        // Stranger attempts duplicate submission with modified URI
        vm.prank(stranger);
        vm.expectEmit(true, true, false, false);
        emit DuplicateSubmissionIgnored(v1Hash, stranger, uint64(block.timestamp));

        registry.submit(v1Hash, v1MerkleRoot, "ipfs://maliciousOverride");

        // Assert state was NOT mutated
        IEvidenceRegistry.PackageRecord memory pkg = registry.getPackage(v1Hash);
        assertEq(pkg.submitter, submitter);
        assertEq(pkg.manifestURI, v1URI);
    }

    function test_ReviewPackageByAuthorizedReviewer() public {
        vm.prank(submitter);
        registry.submit(v1Hash, v1MerkleRoot, v1URI);

        vm.prank(reviewer);
        vm.expectEmit(true, true, false, true);
        emit PackageReviewed(
            v1Hash,
            reviewer,
            IEvidenceRegistry.Decision.NEEDS_EVIDENCE,
            IEvidenceRegistry.ReasonCode.CLOUD_GAP_EXCEEDED,
            v1ReportHash,
            "ipfs://v1Report",
            uint64(block.timestamp)
        );

        registry.review(
            v1Hash,
            IEvidenceRegistry.Decision.NEEDS_EVIDENCE,
            IEvidenceRegistry.ReasonCode.CLOUD_GAP_EXCEEDED,
            v1ReportHash,
            "ipfs://v1Report"
        );

        IEvidenceRegistry.PackageRecord memory pkg = registry.getPackage(v1Hash);
        assertEq(uint8(pkg.latestDecision), uint8(IEvidenceRegistry.Decision.NEEDS_EVIDENCE));
        assertEq(pkg.reviewCount, 1);

        IEvidenceRegistry.ReviewRecord[] memory reviews = registry.getReviews(v1Hash);
        assertEq(reviews.length, 1);
        assertEq(reviews[0].reviewer, reviewer);
        assertEq(reviews[0].reportHash, v1ReportHash);
        assertEq(uint8(reviews[0].reasonCode), uint8(IEvidenceRegistry.ReasonCode.CLOUD_GAP_EXCEEDED));
    }

    function test_RevertReviewUnauthorized() public {
        vm.prank(submitter);
        registry.submit(v1Hash, v1MerkleRoot, v1URI);

        vm.prank(stranger);
        vm.expectRevert(abi.encodeWithSelector(IEvidenceRegistry.UnauthorizedReviewer.selector, stranger));
        registry.review(
            v1Hash,
            IEvidenceRegistry.Decision.APPROVED,
            IEvidenceRegistry.ReasonCode.ALL_CHECKS_PASSED,
            v1ReportHash,
            "ipfs://v1Report"
        );
    }

    function test_RevertReviewUnknownPackage() public {
        vm.prank(reviewer);
        vm.expectRevert(abi.encodeWithSelector(IEvidenceRegistry.UnknownPackage.selector, v1Hash));
        registry.review(
            v1Hash,
            IEvidenceRegistry.Decision.APPROVED,
            IEvidenceRegistry.ReasonCode.ALL_CHECKS_PASSED,
            v1ReportHash,
            "ipfs://v1Report"
        );
    }

    function test_SupersedePackageFlow() public {
        vm.prank(submitter);
        registry.submit(v1Hash, v1MerkleRoot, v1URI);

        vm.prank(reviewer);
        registry.review(
            v1Hash,
            IEvidenceRegistry.Decision.NEEDS_EVIDENCE,
            IEvidenceRegistry.ReasonCode.CLOUD_GAP_EXCEEDED,
            v1ReportHash,
            "ipfs://v1Report"
        );

        // Submitter supersedes v1 with v2
        vm.prank(submitter);
        vm.expectEmit(true, true, true, false);
        emit PackageSuperseded(v1Hash, v2Hash, v2MerkleRoot, submitter, v2URI, uint64(block.timestamp));

        registry.supersede(v2Hash, v1Hash, v2MerkleRoot, v2URI);

        // Verify bidirectional links
        IEvidenceRegistry.PackageRecord memory pkg1 = registry.getPackage(v1Hash);
        IEvidenceRegistry.PackageRecord memory pkg2 = registry.getPackage(v2Hash);

        assertEq(pkg1.supersededBy, v2Hash);
        assertEq(pkg2.prevHash, v1Hash);
        assertEq(pkg2.merkleRoot, v2MerkleRoot);

        // Review v2 as approved
        vm.prank(reviewer);
        registry.review(
            v2Hash,
            IEvidenceRegistry.Decision.APPROVED,
            IEvidenceRegistry.ReasonCode.ALL_CHECKS_PASSED,
            v2ReportHash,
            "ipfs://v2Report"
        );

        // Test single-call lineage chain discovery
        IEvidenceRegistry.PackageRecord[] memory chainFromV1 = registry.getLineageChain(v1Hash);
        IEvidenceRegistry.PackageRecord[] memory chainFromV2 = registry.getLineageChain(v2Hash);

        assertEq(chainFromV1.length, 2);
        assertEq(chainFromV2.length, 2);
        assertEq(chainFromV1[0].packageHash, v1Hash);
        assertEq(chainFromV1[1].packageHash, v2Hash);
        assertEq(chainFromV2[0].packageHash, v1Hash);
        assertEq(chainFromV2[1].packageHash, v2Hash);
    }

    function test_RevertSupersedeByUnauthorizedStranger() public {
        vm.prank(submitter);
        registry.submit(v1Hash, v1MerkleRoot, v1URI);

        vm.prank(stranger);
        vm.expectRevert(abi.encodeWithSelector(IEvidenceRegistry.UnauthorizedSupersede.selector, stranger, submitter));
        registry.supersede(v2Hash, v1Hash, v2MerkleRoot, v2URI);
    }

    function test_RevertSupersedeAlreadySuperseded() public {
        vm.prank(submitter);
        registry.submit(v1Hash, v1MerkleRoot, v1URI);

        vm.prank(submitter);
        registry.supersede(v2Hash, v1Hash, v2MerkleRoot, v2URI);

        bytes32 v3Hash = keccak256("v3");
        bytes32 v3Root = keccak256("v3Root");

        // Attempting to supersede v1 a second time must revert
        vm.prank(submitter);
        vm.expectRevert(abi.encodeWithSelector(IEvidenceRegistry.PackageAlreadySuperseded.selector, v1Hash, v2Hash));
        registry.supersede(v3Hash, v1Hash, v3Root, "ipfs://v3URI");
    }

    function test_RevertSupersedeCycleGriefing() public {
        vm.prank(submitter);
        registry.submit(v1Hash, v1MerkleRoot, v1URI);

        vm.prank(submitter);
        registry.supersede(v2Hash, v1Hash, v2MerkleRoot, v2URI);

        // Attempt to create a cycle (v2 -> v1) must revert because v1 already exists!
        vm.prank(submitter);
        vm.expectRevert(abi.encodeWithSelector(IEvidenceRegistry.PackageAlreadyExists.selector, v1Hash));
        registry.supersede(v1Hash, v2Hash, v1MerkleRoot, v1URI);
    }

    function testFuzz_CannotReviewFromNonReviewer(address caller, bytes32 pkgHash) public {
        vm.assume(!registry.isReviewer(caller));
        vm.assume(pkgHash != bytes32(0));

        vm.prank(caller);
        vm.expectRevert(abi.encodeWithSelector(IEvidenceRegistry.UnauthorizedReviewer.selector, caller));
        registry.review(
            pkgHash,
            IEvidenceRegistry.Decision.APPROVED,
            IEvidenceRegistry.ReasonCode.ALL_CHECKS_PASSED,
            v1ReportHash,
            "ipfs://report"
        );
    }

    function testFuzz_CannotSupersedeFromStranger(address caller, bytes32 h1, bytes32 h2, bytes32 r1, bytes32 r2) public {
        vm.assume(caller != submitter && caller != owner);
        vm.assume(h1 != bytes32(0) && h2 != bytes32(0) && h1 != h2);
        vm.assume(r1 != bytes32(0) && r2 != bytes32(0));

        vm.prank(submitter);
        registry.submit(h1, r1, "uri1");

        vm.prank(caller);
        vm.expectRevert(abi.encodeWithSelector(IEvidenceRegistry.UnauthorizedSupersede.selector, caller, submitter));
        registry.supersede(h2, h1, r2, "uri2");
    }

    function test_WatchdogChallengePackage() public {
        vm.prank(submitter);
        registry.submit(v1Hash, v1MerkleRoot, v1URI);

        bytes32 counterReportHash = keccak256("counterReport");
        address watchdog = address(0xEE5);

        vm.prank(watchdog);
        uint256 challengeId = registry.challengePackage(
            v1Hash,
            IEvidenceRegistry.ReasonCode.INCOMPLETE_SCENE_SELECTION,
            counterReportHash,
            "ipfs://counterReportURI"
        );

        assertEq(challengeId, 0);
        IEvidenceRegistry.DisputeRecord[] memory disputes = registry.getDisputes(v1Hash);
        assertEq(disputes.length, 1);
        assertEq(disputes[0].challenger, watchdog);
        assertEq(uint8(disputes[0].violatedReasonCode), uint8(IEvidenceRegistry.ReasonCode.INCOMPLETE_SCENE_SELECTION));
        assertEq(disputes[0].counterReportHash, counterReportHash);
        assertFalse(disputes[0].resolved);
        assertFalse(disputes[0].upheld);
    }

    function test_ResolveChallengeUpheld() public {
        vm.prank(submitter);
        registry.submit(v1Hash, v1MerkleRoot, v1URI);

        bytes32 counterReportHash = keccak256("counterReport");
        address watchdog = address(0xEE5);

        vm.prank(watchdog);
        registry.challengePackage(
            v1Hash,
            IEvidenceRegistry.ReasonCode.CLOUD_GAP_EXCEEDED,
            counterReportHash,
            "ipfs://counterReportURI"
        );

        // Reviewer upholds the challenge
        vm.prank(reviewer);
        registry.resolveChallenge(
            v1Hash,
            0,
            true,
            IEvidenceRegistry.Decision.NEEDS_EVIDENCE
        );

        IEvidenceRegistry.DisputeRecord[] memory disputes = registry.getDisputes(v1Hash);
        assertTrue(disputes[0].resolved);
        assertTrue(disputes[0].upheld);
        assertEq(disputes[0].resolvedBy, reviewer);

        IEvidenceRegistry.PackageRecord memory pkg = registry.getPackage(v1Hash);
        assertEq(uint8(pkg.latestDecision), uint8(IEvidenceRegistry.Decision.NEEDS_EVIDENCE));
        assertEq(pkg.reviewCount, 1);

        IEvidenceRegistry.ReviewRecord[] memory reviews = registry.getReviews(v1Hash);
        assertEq(reviews.length, 1);
        assertEq(reviews[0].reportHash, counterReportHash);
    }

    function test_RevertChallengeInvalidReason() public {
        vm.prank(submitter);
        registry.submit(v1Hash, v1MerkleRoot, v1URI);

        bytes32 counterReportHash = keccak256("counterReport");

        vm.prank(stranger);
        vm.expectRevert(IEvidenceRegistry.InvalidChallengeReason.selector);
        registry.challengePackage(
            v1Hash,
            IEvidenceRegistry.ReasonCode.ALL_CHECKS_PASSED,
            counterReportHash,
            "ipfs://report"
        );
    }

    function test_RevertResolveChallengeTwice() public {
        vm.prank(submitter);
        registry.submit(v1Hash, v1MerkleRoot, v1URI);

        bytes32 counterReportHash = keccak256("counterReport");

        vm.prank(stranger);
        registry.challengePackage(
            v1Hash,
            IEvidenceRegistry.ReasonCode.SERIAL_OVERLAP_DETECTED,
            counterReportHash,
            "ipfs://report"
        );

        vm.prank(reviewer);
        registry.resolveChallenge(v1Hash, 0, true, IEvidenceRegistry.Decision.NEEDS_EVIDENCE);

        // Second resolution must revert
        vm.prank(reviewer);
        vm.expectRevert(abi.encodeWithSelector(IEvidenceRegistry.ChallengeAlreadyResolved.selector, v1Hash, 0));
        registry.resolveChallenge(v1Hash, 0, true, IEvidenceRegistry.Decision.NEEDS_EVIDENCE);
    }

    function test_RegisterSelectionRule_PreRegistered() public {
        bytes32 ruleHash = keccak256("selectionRule2025");
        bytes32 projectIdHash = keccak256("VCS-1463");
        uint64 windowStart = uint64(block.timestamp + 1000);
        uint64 windowEnd = uint64(block.timestamp + 5000);

        vm.prank(submitter);
        IEvidenceRegistry.TimingStatus status = registry.registerSelectionRule(
            ruleHash,
            projectIdHash,
            windowStart,
            windowEnd,
            "ipfs://rule2025"
        );

        assertEq(uint256(status), uint256(IEvidenceRegistry.TimingStatus.PRE_REGISTERED));

        IEvidenceRegistry.SelectionRuleRecord memory rec = registry.getSelectionRule(ruleHash);
        assertEq(rec.ruleHash, ruleHash);
        assertEq(rec.projectIdHash, projectIdHash);
        assertEq(rec.registeredBy, submitter);
        assertEq(uint256(rec.timingStatus), uint256(IEvidenceRegistry.TimingStatus.PRE_REGISTERED));
    }

    function test_RegisterSelectionRule_PostHoc() public {
        bytes32 ruleHash = keccak256("selectionRule2023Historical");
        bytes32 projectIdHash = keccak256("VCS-1463");
        // Window is in the past (historical monitoring window 2023)
        uint64 windowStart = 1672531200; // 2023-01-01
        uint64 windowEnd = 1704067199;   // 2023-12-31

        // Warp block.timestamp to 2026 (after windowStart)
        vm.warp(1792920000);

        vm.prank(submitter);
        IEvidenceRegistry.TimingStatus status = registry.registerSelectionRule(
            ruleHash,
            projectIdHash,
            windowStart,
            windowEnd,
            "ipfs://rule2023"
        );

        // Current block timestamp is far greater than windowStart
        assertEq(uint256(status), uint256(IEvidenceRegistry.TimingStatus.POST_HOC));

        IEvidenceRegistry.SelectionRuleRecord memory rec = registry.getSelectionRule(ruleHash);
        assertEq(rec.ruleHash, ruleHash);
        assertEq(uint256(rec.timingStatus), uint256(IEvidenceRegistry.TimingStatus.POST_HOC));
    }
}
