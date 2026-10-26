import { createPublicClient, createWalletClient, http } from "viem";
import { privateKeyToAccount } from "viem/accounts";
import { sepolia } from "viem/chains";

const SUBMIT_ABI = [
  {
    type: "function",
    name: "submit",
    inputs: [
      { name: "packageHash", type: "bytes32" },
      { name: "merkleRoot", type: "bytes32" },
      { name: "manifestURI", type: "string" },
    ],
    outputs: [],
    stateMutability: "nonpayable",
  },
] as const;

export default async function handler(req: any, res: any) {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");

  if (req.method === "OPTIONS") {
    res.statusCode = 200;
    res.end();
    return;
  }

  if (req.method !== "POST") {
    res.statusCode = 405;
    res.setHeader("Content-Type", "application/json");
    res.end(JSON.stringify({ error: "Method Not Allowed" }));
    return;
  }

  try {
    let body = req.body;
    if (typeof body === "string") {
      try {
        body = JSON.parse(body);
      } catch {
        body = {};
      }
    }
    body = body || {};

    const { packageHash, merkleRoot, manifestURI, contractAddress } = body;

    if (!/^0x[0-9a-fA-F]{64}$/.test(packageHash || "") || !/^0x[0-9a-fA-F]{64}$/.test(merkleRoot || "")) {
      res.statusCode = 400;
      res.setHeader("Content-Type", "application/json");
      res.end(JSON.stringify({ error: "Invalid packageHash or merkleRoot (must be 0x + 64 hex chars)" }));
      return;
    }

    const rawKey = process.env.DEPLOYER_KEY;
    if (!rawKey) {
      res.statusCode = 500;
      res.setHeader("Content-Type", "application/json");
      res.end(JSON.stringify({ error: "No testnet relayer key configured in environment variables (DEPLOYER_KEY)" }));
      return;
    }

    const pk = (rawKey.startsWith("0x") ? rawKey : `0x${rawKey}`) as `0x${string}`;
    const account = privateKeyToAccount(pk);
    const rpcUrl = process.env.SEPOLIA_RPC_URL || "https://ethereum-sepolia-rpc.publicnode.com";
    const transport = http(rpcUrl, { timeout: 20_000 });

    const publicClient = createPublicClient({ chain: sepolia, transport });
    const walletClient = createWalletClient({ account, chain: sepolia, transport });

    const targetContract = (contractAddress || "0xb1ce2e8ceb392ad3bf0e011d05689058dfa9210f") as `0x${string}`;
    const uri = manifestURI || "browser://ccel-package (export JSON for full envelope)";

    const gas = await publicClient
      .estimateContractGas({
        address: targetContract,
        abi: SUBMIT_ABI,
        functionName: "submit",
        args: [packageHash as `0x${string}`, merkleRoot as `0x${string}`, uri],
        account: account.address,
      })
      .catch(() => 550_000n);

    const txHash = await walletClient.writeContract({
      address: targetContract,
      abi: SUBMIT_ABI,
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
}
