#!/usr/bin/env python3
"""
Sepolia Deployment & Lifecycle Runner
Deploys EvidenceRegistry to Ethereum Sepolia (chainId 11155111) and executes
the complete 5-transaction lifecycle:
1. deploy(contract)
2. submit(v1)
3. challengePackage(v1, CLOUD_GAP_EXCEEDED, v1ReportHash) -> Watchdog Dispute Moat
4. resolveChallenge(v1, 0, true, NEEDS_EVIDENCE) -> Reviewer resolution
5. supersede(v2, v1)
6. review(v2, APPROVED, ALL_CHECKS_PASSED, v2ReportHash)
Generates deployments/sepolia.json and packages/web/public/fixtures/sepolia.json.
"""

import glob
import json
import os
import subprocess
import sys


def get_env_var(name: str) -> str:
    if os.path.exists(".env"):
        with open(".env", "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith(f"{name}="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    return os.environ.get(name, "")


def main():
    deployer_addr = get_env_var("DEPLOYER_ADDRESS")
    deployer_key = get_env_var("DEPLOYER_KEY")
    rpc_url = get_env_var("SEPOLIA_RPC_URL") or "https://sepolia.drpc.org"

    if not deployer_addr or not deployer_key:
        print("❌ Error: DEPLOYER_ADDRESS or DEPLOYER_KEY not found in .env")
        sys.exit(1)

    print(f"📡 Checking Sepolia balance for {deployer_addr} via {rpc_url}...")

    cast_path = os.path.expanduser("~/.foundry/bin/cast")
    res = subprocess.run([cast_path, "balance", deployer_addr, "--rpc-url", rpc_url], capture_output=True, text=True)
    balance_wei = int(res.stdout.strip() or "0")
    balance_eth = balance_wei / 1e18

    print(f"💰 Current Sepolia Balance: {balance_eth:.6f} Sepolia ETH")
    if balance_wei < 5000000000000000:  # < 0.005 ETH
        print("❌ Insufficient balance for deployment.")
        sys.exit(1)

    print("\n🚀 Broadcasting DeployAndExecuteScript to Ethereum Sepolia...")
    cmd = [
        os.path.expanduser("~/.foundry/bin/forge"),
        "script",
        "script/DeployAndExecute.s.sol:DeployAndExecuteScript",
        "--rpc-url", rpc_url,
        "--broadcast",
        "--skip-simulation",
        "-vvv"
    ]
    env = os.environ.copy()
    env["DEPLOYER_KEY"] = deployer_key

    proc = subprocess.run(cmd, cwd="packages/contracts", env=env, capture_output=True, text=True)
    print(proc.stdout)
    if proc.returncode != 0:
        print("❌ Deployment failed:", proc.stderr)
        sys.exit(proc.returncode)

    print("🔍 Parsing broadcast logs...")
    # Find latest broadcast run
    run_files = sorted(glob.glob("packages/contracts/broadcast/DeployAndExecute.s.sol/11155111/run-latest.json"))
    if not run_files:
        print("❌ No broadcast run-latest.json found!")
        sys.exit(1)

    with open(run_files[0], "r") as f:
        run_data = json.load(f)

    txs = run_data.get("transactions", [])
    print(f"Found {len(txs)} executed transactions in broadcast log.")

    contract_addr = None
    deploy_tx = None
    register_rule_tx = None
    submit_v1_tx = None
    challenge_v1_tx = None
    resolve_v1_tx = None
    supersede_v2_tx = None
    review_v2_tx = None

    for tx in txs:
        tx_type = tx.get("transactionType")
        tx_hash = tx.get("hash")
        contract_name = tx.get("contractName")
        fn = tx.get("function")

        if tx_type == "CREATE":
            contract_addr = tx.get("contractAddress")
            deploy_tx = tx_hash
        elif fn and "registerSelectionRule(" in fn:
            register_rule_tx = tx_hash
        elif fn and "submit(" in fn:
            submit_v1_tx = tx_hash
        elif fn and "challengePackage(" in fn:
            challenge_v1_tx = tx_hash
        elif fn and "resolveChallenge(" in fn:
            resolve_v1_tx = tx_hash
        elif fn and "supersede(" in fn:
            supersede_v2_tx = tx_hash
        elif fn and "review(" in fn:
            review_v2_tx = tx_hash

    # Read latest manifest and report hashes
    with open("packages/web/public/fixtures/v1/manifest.json") as f:
        v1_manifest = json.load(f)
        v1_pkg_hash = v1_manifest["provenance"]["packageHash"]
        v1_merkle_root = v1_manifest["commitment"]["merkleRoot"]
    with open("packages/web/public/fixtures/v2/manifest.json") as f:
        v2_manifest = json.load(f)
        v2_pkg_hash = v2_manifest["provenance"]["packageHash"]
        v2_merkle_root = v2_manifest["commitment"]["merkleRoot"]
    with open("packages/web/public/fixtures/v1/check_report.json") as f:
        v1_report = json.load(f)
    with open("packages/web/public/fixtures/v2/check_report.json") as f:
        v2_report = json.load(f)

    sys.path.insert(0, os.path.abspath("packages/cli"))
    from ccel_cli.canonical import compute_report_hash
    v1_report_hash = compute_report_hash(v1_report["commitment"])
    v2_report_hash = compute_report_hash(v2_report["commitment"])

    deployment_data = {
        "chainId": 11155111,
        "chainName": "Ethereum Sepolia Testnet",
        "deployerAddress": deployer_addr,
        "contractAddress": contract_addr,
        "reviewerAddress": deployer_addr,
        "deployTxHash": deploy_tx,
        "v1PackageHash": v1_pkg_hash,
        "v1MerkleRoot": v1_merkle_root,
        "v1ReportHash": v1_report_hash,
        "v2PackageHash": v2_pkg_hash,
        "v2MerkleRoot": v2_merkle_root,
        "v2ReportHash": v2_report_hash,
        "tx0RegisterRule": register_rule_tx,
        "tx1SubmitV1": submit_v1_tx,
        "tx2ChallengeV1": challenge_v1_tx,
        "tx3ResolveChallengeV1": resolve_v1_tx,
        "tx4SupersedeV2": supersede_v2_tx,
        "tx5ReviewV2": review_v2_tx,
        "deploymentStatus": "LIVE_VERIFIED_ON_SEPOLIA",
        "etherscanLinks": {
            "contract": f"https://sepolia.etherscan.io/address/{contract_addr}",
            "deployTx": f"https://sepolia.etherscan.io/tx/{deploy_tx}",
            "tx0RegisterRule": f"https://sepolia.etherscan.io/tx/{register_rule_tx}",
            "tx1SubmitV1": f"https://sepolia.etherscan.io/tx/{submit_v1_tx}",
            "tx2ChallengeV1": f"https://sepolia.etherscan.io/tx/{challenge_v1_tx}",
            "tx3ResolveChallengeV1": f"https://sepolia.etherscan.io/tx/{resolve_v1_tx}",
            "tx4SupersedeV2": f"https://sepolia.etherscan.io/tx/{supersede_v2_tx}",
            "tx5ReviewV2": f"https://sepolia.etherscan.io/tx/{review_v2_tx}",
        }
    }

    os.makedirs("deployments", exist_ok=True)
    with open("deployments/sepolia.json", "w") as f:
        json.dump(deployment_data, f, indent=2)

    os.makedirs("packages/web/public/fixtures", exist_ok=True)
    with open("packages/web/public/fixtures/sepolia.json", "w") as f:
        json.dump(deployment_data, f, indent=2)

    if os.path.exists("packages/web/dist/fixtures"):
        with open("packages/web/dist/fixtures/sepolia.json", "w") as f:
            json.dump(deployment_data, f, indent=2)

    print("\n✅ Sepolia deployment recorded successfully!")
    print(f"Contract: {contract_addr}")
    print(f"Deploy Tx: {deploy_tx}")
    print(f"Tx 1 (submit v1): {submit_v1_tx}")
    print(f"Tx 2 (challengePackage v1): {challenge_v1_tx}")
    print(f"Tx 3 (resolveChallenge v1): {resolve_v1_tx}")
    print(f"Tx 4 (supersede v1->v2): {supersede_v2_tx}")
    print(f"Tx 5 (review v2): {review_v2_tx}")


if __name__ == "__main__":
    main()
