import { defineConfig } from "vite";
import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import { createPublicClient, createWalletClient, http } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { sepolia } from "viem/chains";
import EvidenceRegistryABI from "./src/config/EvidenceRegistryABI.json";

function resolveRepoRoot(): string {
  const cwd = process.cwd();
  if (fs.existsSync(path.resolve(cwd, "packages/cli"))) {
    return cwd;
  }
  return path.resolve(cwd, "../..");
}

function loadRootEnv(): Record<string, string> {
  const root = resolveRepoRoot();
  const candidates = [
    path.resolve(root, ".env"),
    path.resolve(process.cwd(), ".env"),
  ];
  for (const p of candidates) {
    if (fs.existsSync(p)) {
      const lines = fs.readFileSync(p, "utf8").split(/\r?\n/);
      const out: Record<string, string> = {};
      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || trimmed.startsWith("#")) continue;
        const eq = trimmed.indexOf("=");
        if (eq > 0) {
          const k = trimmed.slice(0, eq).trim();
          const v = trimmed.slice(eq + 1).trim().replace(/^['"]|['"]$/g, "");
          out[k] = v;
        }
      }
      return out;
    }
  }
  return {};
}

function runPythonSatelliteProcessor(payload: Record<string, any>): Promise<any> {
  return new Promise((resolve, reject) => {
    const repoRoot = resolveRepoRoot();
    const venvPy = path.resolve(repoRoot, ".venv/bin/python3");
    const pyBin = fs.existsSync(venvPy) ? venvPy : "python3";

    const safeSlug = String(payload.caseId || "custom-case")
      .trim()
      .replace(/[^a-zA-Z0-9_-]/g, "-");
    const outDir = path.resolve(repoRoot, "packages/web/public/fixtures/custom", safeSlug);
    const urlPrefix = `/fixtures/custom/${safeSlug}`;

    const fullPayload = {
      ...payload,
      caseId: safeSlug,
      outDir,
      urlPrefix,
    };

    const child = spawn(pyBin, ["-m", "ccel_cli.live_satellite"], {
      cwd: repoRoot,
      env: {
        ...process.env,
        PYTHONPATH: path.resolve(repoRoot, "packages/cli"),
      },
    });

    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (chunk) => {
      stdout += String(chunk);
    });
    child.stderr.on("data", (chunk) => {
      stderr += String(chunk);
    });
    child.on("error", (err) => reject(err));
    child.on("close", (code) => {
      if (code !== 0 && !stdout.trim()) {
        reject(new Error(stderr.trim() || `Python processor exited with code ${code}`));
        return;
      }
      try {
        const lines = stdout.trim().split(/\r?\n/);
        const lastJsonLine = lines[lines.length - 1];
        resolve(JSON.parse(lastJsonLine));
      } catch (e: any) {
        reject(new Error(`Failed to parse satellite processor JSON: ${e?.message || e} (${stderr.trim()})`));
      }
    });

    child.stdin.write(JSON.stringify(fullPayload));
    child.stdin.end();
  });
}

function sepoliaAnchorPlugin() {
  const handler = async (req: any, res: any, next: any) => {
    if (req.method !== "POST") {
      return next();
    }

    if (req.url === "/api/process-satellite") {
      try {
        let body = "";
        for await (const chunk of req) body += chunk;
        const payload = JSON.parse(body || "{}");
        const result = await runPythonSatelliteProcessor(payload);
        res.statusCode = 200;
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify(result));
      } catch (err: any) {
        res.statusCode = 500;
        res.setHeader("Content-Type", "application/json");
        res.end(
          JSON.stringify({
            status: "UNSUPPORTED_DATA",
            verdict: "NEEDS_EVIDENCE",
            errorReason: err?.message || String(err),
          })
        );
      }
      return;
    }

    if (req.url === "/api/anchor-sepolia") {
      try {
        let body = "";
        for await (const chunk of req) body += chunk;
        const { packageHash, merkleRoot, manifestURI, contractAddress } = JSON.parse(body || "{}");

        if (!/^0x[0-9a-fA-F]{64}$/.test(packageHash || "") || !/^0x[0-9a-fA-F]{64}$/.test(merkleRoot || "")) {
          res.statusCode = 400;
          res.setHeader("Content-Type", "application/json");
          res.end(JSON.stringify({ error: "Invalid packageHash or merkleRoot (must be 0x + 64 hex chars)" }));
          return;
        }

        const env = loadRootEnv();
        const rawKey = process.env.DEPLOYER_KEY || env.DEPLOYER_KEY;
        if (!rawKey) {
          res.statusCode = 500;
          res.setHeader("Content-Type", "application/json");
          res.end(JSON.stringify({ error: "No testnet relayer key configured in .env" }));
          return;
        }

        const pk = (rawKey.startsWith("0x") ? rawKey : `0x${rawKey}`) as `0x${string}`;
        const account = privateKeyToAccount(pk);
        const rpcUrl = "https://ethereum-sepolia-rpc.publicnode.com";
        const transport = http(rpcUrl, { timeout: 20_000 });

        const publicClient = createPublicClient({ chain: sepolia, transport });
        const walletClient = createWalletClient({ account, chain: sepolia, transport });

        const targetContract = (contractAddress || "0xb1ce2e8ceb392ad3bf0e011d05689058dfa9210f") as `0x${string}`;
        const uri = manifestURI || "browser://ccel-package (export JSON for full envelope)";

        const gas = await publicClient
          .estimateContractGas({
            address: targetContract,
            abi: EvidenceRegistryABI as any,
            functionName: "submit",
            args: [packageHash as `0x${string}`, merkleRoot as `0x${string}`, uri],
            account: account.address,
          })
          .catch(() => 550_000n);

        const txHash = await walletClient.writeContract({
          address: targetContract,
          abi: EvidenceRegistryABI as any,
          functionName: "submit",
          args: [packageHash as `0x${string}`, merkleRoot as `0x${string}`, uri],
          account,
          gas: (gas * 120n) / 100n,
        });

        res.statusCode = 200;
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify({ txHash, relayer: account.address }));
      } catch (err: any) {
        res.statusCode = 500;
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify({ error: err?.shortMessage || err?.message || String(err) }));
      }
      return;
    }

    if (req.url === "/api/review-sepolia") {
      try {
        let body = "";
        for await (const chunk of req) body += chunk;
        const {
          packageHash,
          decision,
          reasonCode,
          reportHash,
          reportURI,
          allGatesPassed,
          contractAddress,
        } = JSON.parse(body || "{}");

        if (!/^0x[0-9a-fA-F]{64}$/.test(packageHash || "") || !/^0x[0-9a-fA-F]{64}$/.test(reportHash || "")) {
          res.statusCode = 400;
          res.setHeader("Content-Type", "application/json");
          res.end(JSON.stringify({ error: "Invalid packageHash or reportHash (must be 0x + 64 hex chars)" }));
          return;
        }

        const decisionNum = Number(decision);
        if (decisionNum === 1 && !allGatesPassed) {
          res.statusCode = 400;
          res.setHeader("Content-Type", "application/json");
          res.end(
            JSON.stringify({
              error:
                "Protocol Guard: Cannot anchor Decision.APPROVED on-chain unless all 5 satellite quality gates pass on verified raster output.",
            })
          );
          return;
        }

        const env = loadRootEnv();
        const rawKey = process.env.DEPLOYER_KEY || env.DEPLOYER_KEY;
        if (!rawKey) {
          res.statusCode = 500;
          res.setHeader("Content-Type", "application/json");
          res.end(JSON.stringify({ error: "No testnet reviewer key configured in .env" }));
          return;
        }

        const pk = (rawKey.startsWith("0x") ? rawKey : `0x${rawKey}`) as `0x${string}`;
        const account = privateKeyToAccount(pk);
        const rpcUrl = "https://ethereum-sepolia-rpc.publicnode.com";
        const transport = http(rpcUrl, { timeout: 20_000 });

        const publicClient = createPublicClient({ chain: sepolia, transport });
        const walletClient = createWalletClient({ account, chain: sepolia, transport });

        const targetContract = (contractAddress || "0xb1ce2e8ceb392ad3bf0e011d05689058dfa9210f") as `0x${string}`;
        const rCode = Number(reasonCode || 0);
        const uri = reportURI || "ccel://check-report/v1";

        const gas = await publicClient
          .estimateContractGas({
            address: targetContract,
            abi: EvidenceRegistryABI as any,
            functionName: "review",
            args: [packageHash as `0x${string}`, decisionNum, rCode, reportHash as `0x${string}`, uri],
            account: account.address,
          })
          .catch(() => 450_000n);

        const txHash = await walletClient.writeContract({
          address: targetContract,
          abi: EvidenceRegistryABI as any,
          functionName: "review",
          args: [packageHash as `0x${string}`, decisionNum, rCode, reportHash as `0x${string}`, uri],
          account,
          gas: (gas * 120n) / 100n,
        });

        res.statusCode = 200;
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify({ txHash, reviewer: account.address, decision: decisionNum }));
      } catch (err: any) {
        res.statusCode = 500;
        res.setHeader("Content-Type", "application/json");
        res.end(JSON.stringify({ error: err?.shortMessage || err?.message || String(err) }));
      }
      return;
    }

    return next();
  };

  return {
    name: "ccel-sepolia-anchor-relayer",
    configureServer(server: any) {
      server.middlewares.use(handler);
    },
    configurePreviewServer(server: any) {
      server.middlewares.use(handler);
    },
  };
}

export default defineConfig({
  plugins: [sepoliaAnchorPlugin()],
});
