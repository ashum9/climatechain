// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.24;

import {Script, console2} from "forge-std/Script.sol";
import {IEvidenceRegistry} from "../src/IEvidenceRegistry.sol";
import {EvidenceRegistry} from "../src/EvidenceRegistry.sol";

contract DeployAndExecuteScript is Script {
    bytes32 constant V1_PACKAGE_HASH = 0x4030177336e456e398419c05a34f41d1d816246c79e186b8f11d9c130a479c44;
    bytes32 constant V1_MERKLE_ROOT = 0x3cb222c9ba5d6dd99ebac7d51d1ff40ee8c5530e0a108d83a6f3e2a7f0e48ca4;
    bytes32 constant V1_REPORT_HASH = 0xaf14a22a561c5461a2af23faa4de18c2a3bb1ca6be799ca0ac9c6e68b08723ec;

    bytes32 constant V2_PACKAGE_HASH = 0xc19fd3bb3010a458dc709fc9b555d1ea23010dfa39162c7346d3e76619fe0b4f;
    bytes32 constant V2_MERKLE_ROOT = 0xd7c05e6e8c8414e43d8878dd23784740b7bd652b0a03470d5b2f237a09d65f92;
    bytes32 constant V2_REPORT_HASH = 0x46c84a1ef864ea59ebe021bc7016217ea0647c232437722b4b96e39f852e4d6d;

    function run() external {
        uint256 deployerPrivateKey = vm.envUint("DEPLOYER_KEY");
        address deployer = vm.addr(deployerPrivateKey);

        console2.log("Executing deployment and audit lifecycle from:", deployer);

        vm.startBroadcast(deployerPrivateKey);

        // 1. Deploy EvidenceRegistry with deployer as initial reviewer
        EvidenceRegistry registry = new EvidenceRegistry(deployer);
        address contractAddr = address(registry);
        console2.log("EvidenceRegistry deployed at:", contractAddr);

        // 2. Pre-register selection rule (honest POST_HOC designation on Sepolia for historical 2023 period)
        bytes32 ruleHash = keccak256("DEFAULT_SELECTION_RULE_VCS1463_2023");
        bytes32 projectIdHash = keccak256("VCS-1463");
        registry.registerSelectionRule(
            ruleHash,
            projectIdHash,
            1672531200, // 2023-01-01
            1704067199, // 2023-12-31
            "ipfs://selection_rule_vcs1463_2023"
        );
        console2.log("Tx 0 (registerSelectionRule) executed with ruleHash:", vm.toString(ruleHash));

        // 2. Tx 1: Submit v1
        registry.submit(V1_PACKAGE_HASH, V1_MERKLE_ROOT, "ipfs://v1_manifest");
        console2.log("Tx 1 (submit v1) executed");

        // 3. Tx 2: Watchdog Dispute Challenge against v1 (Independent Dispute Protocol)
        uint256 challengeId = registry.challengePackage(
            V1_PACKAGE_HASH,
            IEvidenceRegistry.ReasonCode.CLOUD_GAP_EXCEEDED,
            V1_REPORT_HASH,
            "ipfs://v1_watchdog_counter_report"
        );
        console2.log("Tx 2 (challengePackage v1) executed with challengeId:", challengeId);

        // 4. Tx 3: Reviewer resolves challenge (upholds dispute -> sets decision to NEEDS_EVIDENCE)
        registry.resolveChallenge(
            V1_PACKAGE_HASH,
            challengeId,
            true,
            IEvidenceRegistry.Decision.NEEDS_EVIDENCE
        );
        console2.log("Tx 3 (resolveChallenge v1 -> NEEDS_EVIDENCE) executed");

        // 5. Tx 4: Supersede v1 with v2
        registry.supersede(V2_PACKAGE_HASH, V1_PACKAGE_HASH, V2_MERKLE_ROOT, "ipfs://v2_manifest");
        console2.log("Tx 4 (supersede v1 -> v2) executed");

        // 6. Tx 5: Review v2 (APPROVED, ALL_CHECKS_PASSED)
        registry.review(
            V2_PACKAGE_HASH,
            IEvidenceRegistry.Decision.APPROVED,
            IEvidenceRegistry.ReasonCode.ALL_CHECKS_PASSED,
            V2_REPORT_HASH,
            "ipfs://v2_check_report"
        );
        console2.log("Tx 5 (review v2 -> APPROVED) executed");

        vm.stopBroadcast();
    }
}
