import { createPublicClient, http, custom, fallback } from "viem";
import { sepolia } from "viem/chains";
import {
  EVIDENCE_REGISTRY_ABI,
  SEPOLIA_CHAIN_ID,
  SEPOLIA_RPC_URLS,
} from "../config/chain";

export function getSepoliaPublicClient() {
  const transports = SEPOLIA_RPC_URLS.map((url) => http(url));
  return createPublicClient({
    chain: sepolia,
    transport: fallback(transports),
  });
}

export async function checkIsReviewer(
  contractAddress: `0x${string}`,
  reviewerAddress: `0x${string}`
): Promise<boolean> {
  const client = getSepoliaPublicClient();
  try {
    const res = await client.readContract({
      address: contractAddress,
      abi: EVIDENCE_REGISTRY_ABI,
      functionName: "isReviewer",
      args: [reviewerAddress],
    });
    return Boolean(res);
  } catch (err) {
    console.warn("Could not query isReviewer on-chain:", err);
    return false;
  }
}

export async function fetchLineageFromSepolia(
  contractAddress: `0x${string}`,
  packageHash: `0x${string}`
): Promise<any[]> {
  const client = getSepoliaPublicClient();
  try {
    const chain = await client.readContract({
      address: contractAddress,
      abi: EVIDENCE_REGISTRY_ABI,
      functionName: "getLineageChain",
      args: [packageHash],
    });
    return chain as any[];
  } catch (err) {
    console.warn("Could not fetch lineage from Sepolia:", err);
    return [];
  }
}

export async function fetchReviewsFromSepolia(
  contractAddress: `0x${string}`,
  packageHash: `0x${string}`
): Promise<any[]> {
  const client = getSepoliaPublicClient();
  try {
    const reviews = await client.readContract({
      address: contractAddress,
      abi: EVIDENCE_REGISTRY_ABI,
      functionName: "getReviews",
      args: [packageHash],
    });
    return reviews as any[];
  } catch (err) {
    console.warn("Could not fetch reviews from Sepolia:", err);
    return [];
  }
}

export async function fetchDisputesFromSepolia(
  contractAddress: `0x${string}`,
  packageHash: `0x${string}`
): Promise<any[]> {
  const client = getSepoliaPublicClient();
  try {
    const disputes = await client.readContract({
      address: contractAddress,
      abi: EVIDENCE_REGISTRY_ABI,
      functionName: "getDisputes",
      args: [packageHash],
    });
    return disputes as any[];
  } catch (err) {
    console.warn("Could not fetch disputes from Sepolia:", err);
    return [];
  }
}

export async function submitReviewTransaction(
  contractAddress: `0x${string}`,
  packageHash: `0x${string}`,
  decision: number,
  reasonCode: number,
  reportHash: `0x${string}`,
  reportURI: string
): Promise<string> {
  if (typeof (window as any).ethereum === "undefined") {
    throw new Error("No EIP-1193 wallet (e.g. MetaMask) detected in browser");
  }

  const ethereum = (window as any).ethereum;
  const accounts: string[] = await ethereum.request({
    method: "eth_requestAccounts",
  });
  if (!accounts || accounts.length === 0) {
    throw new Error("User denied wallet connection");
  }

  const chainIdHex = await ethereum.request({ method: "eth_chainId" });
  const currentChainId = parseInt(chainIdHex, 16);
  if (currentChainId !== SEPOLIA_CHAIN_ID) {
    try {
      await ethereum.request({
        method: "wallet_switchEthereumChain",
        params: [{ chainId: `0x${SEPOLIA_CHAIN_ID.toString(16)}` }],
      });
    } catch (switchErr) {
      throw new Error("Please switch your wallet to Ethereum Sepolia Testnet");
    }
  }

  const { createWalletClient } = await import("viem");
  const walletClient = createWalletClient({
    chain: sepolia,
    transport: custom(ethereum),
  });

  const txHash = await walletClient.writeContract({
    address: contractAddress,
    abi: EVIDENCE_REGISTRY_ABI,
    functionName: "review",
    args: [packageHash, decision, reasonCode, reportHash, reportURI],
    account: accounts[0] as `0x${string}`,
  });

  return txHash;
}

export async function submitChallengeTransaction(
  contractAddress: `0x${string}`,
  packageHash: `0x${string}`,
  violatedReasonCode: number,
  counterReportHash: `0x${string}`,
  evidenceURI: string
): Promise<string> {
  if (typeof (window as any).ethereum === "undefined") {
    throw new Error("No EIP-1193 wallet (e.g. MetaMask) detected in browser");
  }

  const ethereum = (window as any).ethereum;
  const accounts: string[] = await ethereum.request({
    method: "eth_requestAccounts",
  });
  if (!accounts || accounts.length === 0) {
    throw new Error("User denied wallet connection");
  }

  const { createWalletClient } = await import("viem");
  const walletClient = createWalletClient({
    chain: sepolia,
    transport: custom(ethereum),
  });

  const txHash = await walletClient.writeContract({
    address: contractAddress,
    abi: EVIDENCE_REGISTRY_ABI,
    functionName: "challengePackage",
    args: [packageHash, violatedReasonCode, counterReportHash, evidenceURI],
    account: accounts[0] as `0x${string}`,
  });

  return txHash;
}

export async function submitResolveChallengeTransaction(
  contractAddress: `0x${string}`,
  packageHash: `0x${string}`,
  challengeId: bigint,
  uphold: boolean,
  updatedDecision: number
): Promise<string> {
  if (typeof (window as any).ethereum === "undefined") {
    throw new Error("No EIP-1193 wallet (e.g. MetaMask) detected in browser");
  }

  const ethereum = (window as any).ethereum;
  const accounts: string[] = await ethereum.request({
    method: "eth_requestAccounts",
  });
  if (!accounts || accounts.length === 0) {
    throw new Error("User denied wallet connection");
  }

  const { createWalletClient } = await import("viem");
  const walletClient = createWalletClient({
    chain: sepolia,
    transport: custom(ethereum),
  });

  const txHash = await walletClient.writeContract({
    address: contractAddress,
    abi: EVIDENCE_REGISTRY_ABI,
    functionName: "resolveChallenge",
    args: [packageHash, challengeId, uphold, updatedDecision],
    account: accounts[0] as `0x${string}`,
  });

  return txHash;
}
