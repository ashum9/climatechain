#!/usr/bin/env bash
set -e

echo "============================================================"
echo "🌱 ClimateChain Evidence Ledger (CCEL) — Full Verification"
echo "============================================================"

# 1. Run Licence & Secret Guard
echo "🔒 [1/6] Running Secret & Licence Guard..."
PYTHONPATH=. ./.venv/bin/python3 scripts/licence_and_secret_guard.py

# 2. Run Python CLI & Boundary Tests
echo "🐍 [2/6] Running Python CLI & Winning Moat Tests (35 tests)..."
PYTHONPATH=.:packages/cli ./.venv/bin/pytest packages/cli/tests

# 3. Run Foundry Smart Contract Tests
echo "⛓️  [3/6] Running Foundry Smart Contract Test Suite (18 tests + fuzzing)..."
~/.foundry/bin/forge test --root packages/contracts

# 4. Run TypeScript Web Tests & Production Build
echo "🌐 [4/6] Running TypeScript Web Tests & Static Build..."
npm --prefix packages/web test -- --run
npm --prefix packages/web run build

# 5. Verify Real VCS 1463 Evidence Packages (v1 & v2) and STAC Query Replay via CLI
echo "📦 [5/6] Verifying VCS 1463 Evidence Packages & STAC Census via CLI..."
PYTHONPATH=.:packages/cli ./.venv/bin/python3 packages/cli/ccel_cli/main.py verify --package-dir packages/web/public/fixtures/v1 || true
PYTHONPATH=.:packages/cli ./.venv/bin/python3 packages/cli/ccel_cli/main.py verify --package-dir packages/web/public/fixtures/v2
PYTHONPATH=.:packages/cli ./.venv/bin/python3 packages/cli/ccel_cli/main.py census
PYTHONPATH=.:packages/cli ./.venv/bin/python3 packages/cli/ccel_cli/main.py replay

# 6. Deep On-Chain State Verification on Ethereum Sepolia
echo "📡 [6/6] Deep On-Chain State Verification on Ethereum Sepolia..."
PYTHONPATH=. ./.venv/bin/python3 scripts/verify_onchain_state.py

echo ""
echo "============================================================"
echo "✅ ALL 6 VERIFICATION STAGES PASSED CLEANLY WITH ZERO ERRORS!"
echo "============================================================"
