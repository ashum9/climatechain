/**
 * RFC 8785 (JSON Canonicalization Scheme - JCS) & RFC 6962 Domain-Separated Merkle Tree
 * Browser & Node compatible (using standard WebCrypto API).
 */

export function canonicalizeJsonStr(val: any): string {
  if (val === null) {
    return "null";
  }
  if (typeof val === "boolean") {
    return val ? "true" : "false";
  }
  if (typeof val === "number") {
    if (!Number.isFinite(val)) {
      throw new Error("NaN and Infinity are not permitted in RFC 8785 JSON");
    }
    if (Object.is(val, -0) || val === 0) {
      return "0";
    }
    return val.toString();
  }
  if (typeof val === "string") {
    return JSON.stringify(val);
  }
  if (Array.isArray(val)) {
    return "[" + val.map((v) => canonicalizeJsonStr(v)).join(",") + "]";
  }
  if (typeof val === "object") {
    // Sort keys lexicographically by UTF-16 code units
    const keys = Object.keys(val).sort((a, b) => {
      const minLen = Math.min(a.length, b.length);
      for (let i = 0; i < minLen; i++) {
        const ca = a.charCodeAt(i);
        const cb = b.charCodeAt(i);
        if (ca !== cb) return ca - cb;
      }
      return a.length - b.length;
    });

    const entries = keys.map((k) => `${JSON.stringify(k)}:${canonicalizeJsonStr(val[k])}`);
    return "{" + entries.join(",") + "}";
  }
  throw new TypeError(`Cannot serialize type ${typeof val} to RFC 8785 JSON`);
}

export function canonicalizeJsonBytes(val: any): Uint8Array {
  return new TextEncoder().encode(canonicalizeJsonStr(val));
}

export async function sha256(data: Uint8Array): Promise<Uint8Array> {
  const hashBuf = await globalThis.crypto.subtle.digest("SHA-256", data as any);
  return new Uint8Array(hashBuf);
}

export function toHex(bytes: Uint8Array): string {
  return Array.from(bytes)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export function fromHex(hexStr: string): Uint8Array {
  const clean = hexStr.replace(/^0x/, "");
  const out = new Uint8Array(clean.length / 2);
  for (let i = 0; i < clean.length; i += 2) {
    out[i / 2] = parseInt(clean.substring(i, i + 2), 16);
  }
  return out;
}

export async function hashLeaf(leafId: string, payload: any): Promise<Uint8Array> {
  const payloadBytes =
    payload instanceof Uint8Array ? payload : canonicalizeJsonBytes(payload);
  const leafIdBytes = new TextEncoder().encode(leafId);

  // Buffer: 0x00 || leafId || 0x00 || payloadBytes
  const total = new Uint8Array(1 + leafIdBytes.length + 1 + payloadBytes.length);
  total[0] = 0x00;
  total.set(leafIdBytes, 1);
  total[1 + leafIdBytes.length] = 0x00;
  total.set(payloadBytes, 1 + leafIdBytes.length + 1);

  return await sha256(total);
}

export async function hashNode(left: Uint8Array, right: Uint8Array): Promise<Uint8Array> {
  // Buffer: 0x01 || left || right
  const total = new Uint8Array(1 + left.length + right.length);
  total[0] = 0x01;
  total.set(left, 1);
  total.set(right, 1 + left.length);
  return await sha256(total);
}

export interface MerkleLeafEntry {
  leafId: string;
  payload: any;
}

export interface MerkleProofStep {
  position: "left" | "right";
  hash: string;
}

export class MerkleTreeBrowser {
  leafEntries: MerkleLeafEntry[];
  leafIds: string[];
  leafHashes: Uint8Array[] = [];
  layers: Uint8Array[][] = [];
  root: Uint8Array = new Uint8Array(32);

  private constructor(entries: MerkleLeafEntry[]) {
    this.leafEntries = entries.sort((a, b) => (a.leafId < b.leafId ? -1 : a.leafId > b.leafId ? 1 : 0));
    this.leafIds = this.leafEntries.map((e) => e.leafId);
  }

  static async create(entries: MerkleLeafEntry[]): Promise<MerkleTreeBrowser> {
    const tree = new MerkleTreeBrowser(entries);
    for (const entry of tree.leafEntries) {
      tree.leafHashes.push(await hashLeaf(entry.leafId, entry.payload));
    }
    tree.layers.push(tree.leafHashes);

    let current = tree.leafHashes;
    while (current.length > 1) {
      const nextLayer: Uint8Array[] = [];
      for (let i = 0; i < current.length; i += 2) {
        if (i + 1 < current.length) {
          nextLayer.push(await hashNode(current[i], current[i + 1]));
        } else {
          // RFC 6962 promotion of odd node
          nextLayer.push(current[i]);
        }
      }
      tree.layers.push(nextLayer);
      current = nextLayer;
    }

    tree.root = current.length > 0 ? current[0] : new Uint8Array(32);
    return tree;
  }

  get rootHex(): string {
    return "0x" + toHex(this.root);
  }

  getLeafHex(leafId: string): string {
    const idx = this.leafIds.indexOf(leafId);
    if (idx === -1) throw new Error(`Leaf ${leafId} not found`);
    return "0x" + toHex(this.leafHashes[idx]);
  }

  getProof(leafId: string): MerkleProofStep[] {
    let idx = this.leafIds.indexOf(leafId);
    if (idx === -1) throw new Error(`Leaf ${leafId} not found`);

    const proof: MerkleProofStep[] = [];
    for (let l = 0; l < this.layers.length - 1; l++) {
      const layer = this.layers[l];
      const isRight = idx % 2 === 1;
      const siblingIdx = isRight ? idx - 1 : idx + 1;
      if (siblingIdx < layer.length) {
        proof.push({
          position: isRight ? "left" : "right",
          hash: "0x" + toHex(layer[siblingIdx]),
        });
      }
      idx = Math.floor(idx / 2);
    }
    return proof;
  }
}

export async function verifyMerkleProof(
  leafId: string,
  payload: any,
  proof: MerkleProofStep[],
  rootHex: string
): Promise<boolean> {
  let current = await hashLeaf(leafId, payload);
  for (const step of proof) {
    const sibling = fromHex(step.hash);
    if (step.position === "left") {
      current = await hashNode(sibling, current);
    } else {
      current = await hashNode(current, sibling);
    }
  }
  return "0x" + toHex(current).toLowerCase() === rootHex.toLowerCase();
}

export async function computePackageHash(commitment: any): Promise<string> {
  const canonBytes = canonicalizeJsonBytes(commitment);
  const hashBytes = await sha256(canonBytes);
  return "0x" + toHex(hashBytes);
}
