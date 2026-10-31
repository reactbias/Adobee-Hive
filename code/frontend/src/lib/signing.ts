// Signing an application to join a hub, in the browser. The private key is made here and never leaves the page
// unless the person saves it. The hub verifies the signature over its own canonical JSON (hive.canonical: sorted
// keys, no spaces, unicode as is), so these bytes have to match it exactly or every signature is refused. Python
// writes 1.0 where JavaScript writes 1, so an application carries whole numbers only.

type Json = null | boolean | number | string | Json[] | { [key: string]: Json };

function sorted(value: unknown): Json {
  if (Array.isArray(value)) return value.map(sorted);
  if (value && typeof value === "object")
    return Object.fromEntries(
      Object.keys(value)
        .sort()
        .filter((key) => (value as Record<string, unknown>)[key] !== undefined)
        .map((key) => [key, sorted((value as Record<string, unknown>)[key])]),
    );
  return value as Json;
}

/** The hub's canonical form of a document, without the keys in `omit` at the top level. */
export function canonical(value: Record<string, unknown>, omit: string[] = []): string {
  const kept = Object.fromEntries(Object.entries(value).filter(([key]) => !omit.includes(key)));
  return JSON.stringify(sorted(kept));
}

const toBase64 = (bytes: ArrayBuffer | Uint8Array) => btoa(String.fromCharCode(...new Uint8Array(bytes)));
export const fromBase64 = (text: string) => Uint8Array.from(atob(text), (c) => c.charCodeAt(0));

export interface Keys {
  /** Base64 of the raw 32-byte Ed25519 public key, as the hub pins it. */
  publicKey: string;
  privateKey: CryptoKey;
  /** The private half as PKCS#8 PEM, for the person to save. Losing it means losing control of the entity. */
  pem: string;
}

/** A fresh Ed25519 keypair, or null where this browser cannot make one. */
export async function generateKeys(): Promise<Keys | null> {
  try {
    const pair = (await crypto.subtle.generateKey({ name: "Ed25519" }, true, ["sign", "verify"])) as CryptoKeyPair;
    const raw = await crypto.subtle.exportKey("raw", pair.publicKey);
    const pkcs8 = toBase64(await crypto.subtle.exportKey("pkcs8", pair.privateKey));
    const pem = `-----BEGIN PRIVATE KEY-----\n${pkcs8.match(/.{1,64}/g)!.join("\n")}\n-----END PRIVATE KEY-----\n`;
    return { publicKey: toBase64(raw), privateKey: pair.privateKey, pem };
  } catch {
    return null;
  }
}

/** Base64 Ed25519 signature over the canonical JSON of the application without its `signature`. */
export async function signApplication(application: Record<string, unknown>, key: CryptoKey): Promise<string> {
  const bytes = new TextEncoder().encode(canonical(application, ["signature"]));
  return toBase64(await crypto.subtle.sign({ name: "Ed25519" }, key, bytes));
}
