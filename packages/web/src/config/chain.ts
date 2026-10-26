import EvidenceRegistryABI from "./EvidenceRegistryABI.json";

export const SEPOLIA_CHAIN_ID = 11155111;

export const SEPOLIA_RPC_URLS = [
  "https://sepolia.drpc.org",
  "https://1rpc.io/sepolia",
  "https://ethereum-sepolia-rpc.publicnode.com",
];

export const VCS_1463_PINNED_KML_SHA256 =
  "6c23a771351e6c3f04473a1af3d6d691819d07d0408ffd159808aacbffcba214";

export const EVIDENCE_REGISTRY_ABI = EvidenceRegistryABI;

export interface DeploymentConfig {
  contractAddress: string;
  reviewerAddress: string;
  deployTxHash: string;
  v1PackageHash: string;
  v2PackageHash: string;
  tx1Hash: string;
  tx2Hash: string;
  tx3Hash: string;
  tx4Hash: string;
}

export async function loadDeploymentConfig(): Promise<DeploymentConfig | null> {
  try {
    const res = await fetch("./fixtures/sepolia.json");
    if (res.ok) {
      return await res.json();
    }
  } catch {
    // Deploy config not generated yet
  }
  return null;
}
