import { describe, expect, it } from "vitest";
import { canonical, fromBase64, generateKeys, signApplication } from "./signing";

describe("the bytes an applicant signs", () => {
  it("are the hub's canonical JSON: sorted keys at every depth, no spaces, unicode kept as is", () => {
    // What seed_vaults.canonical (and hive.canonical) prints for the same value.
    expect(canonical({ b: [1, { z: "Zürich", a: 'x"y\n' }], a: "" })).toBe(
      '{"a":"","b":[1,{"a":"x\\"y\\n","z":"Zürich"}]}',
    );
  });

  it("leave the signature itself out", () => {
    expect(canonical({ entity: { id: "a" }, signature: "abc" }, ["signature"])).toBe('{"entity":{"id":"a"}}');
  });
});

describe("a key made in the browser", () => {
  it("signs an application its public half verifies, and the private half can be saved", async () => {
    const keys = await generateKeys();
    expect(keys).not.toBeNull();
    const application = { entity: { id: "ada", kind: "person", name: "Ada" }, public_key: keys!.publicKey, proofs: [] };
    const signature = await signApplication(application, keys!.privateKey);

    const pub = await crypto.subtle.importKey("raw", fromBase64(keys!.publicKey), { name: "Ed25519" }, false, [
      "verify",
    ]);
    const bytes = new TextEncoder().encode(canonical(application));
    expect(await crypto.subtle.verify({ name: "Ed25519" }, pub, fromBase64(signature), bytes)).toBe(true);
    expect(fromBase64(keys!.publicKey)).toHaveLength(32);
    expect(keys!.pem).toMatch(/^-----BEGIN PRIVATE KEY-----\n[A-Za-z0-9+/=\n]+\n-----END PRIVATE KEY-----\n$/);
  });
});
