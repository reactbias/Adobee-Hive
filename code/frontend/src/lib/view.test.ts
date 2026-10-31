import { describe, expect, it } from "vitest";
import { hubIn, hubUrlIn, isHybrid, viewIn, without } from "./view";

// One rule for `?admin` and `?hub=`: the address decides the view, and no address claims two views at once.

describe("which view an address asks for", () => {
  it("is the hub's own panel for ?admin, and the app for everything else", () => {
    expect(viewIn("?admin")).toBe("admin");
    expect(viewIn("?admin=1")).toBe("admin");
    expect(viewIn("")).toBe("app");
    expect(viewIn("?demo")).toBe("app");
    expect(viewIn("?hub=basel")).toBe("app");
  });

  it("is not decided by the hash, which only ever names a place on the app's page", () => {
    expect(viewIn("?demo")).toBe("app");
    expect(isHybrid("?admin", "#travel")).toBe(true);
    expect(isHybrid("?admin", "")).toBe(false);
    expect(isHybrid("?admin", "#")).toBe(false);
    expect(isHybrid("?demo", "#travel")).toBe(false);
  });
});

describe("the hub an address picks", () => {
  it("skips the finder when it names one", () => {
    expect(hubIn("?hub=zurich")).toBe("zurich");
  });

  it("means this backend when it is written as the short form", () => {
    expect(hubIn("?hub")).toBe("local");
    expect(hubIn("?hub=")).toBe("local");
  });

  it("is nothing at all when the address does not mention one", () => {
    expect(hubIn("")).toBe("");
    expect(hubIn("?demo")).toBe("");
  });

  it("carries a base URL for a hub this app has never heard of", () => {
    expect(hubUrlIn("?hub=zurich&hub_url=http%3A%2F%2F10.0.0.2%3A8461")).toBe("http://10.0.0.2:8461");
    expect(hubUrlIn("?hub=zurich")).toBe("");
  });
});

describe("taking a parameter out of an address", () => {
  it("leaves the others, and the path, alone", () => {
    const url = new URL("http://host/app/?demo&admin&hub=basel");
    expect(without(url, "admin")).toBe("/app/?demo&hub=basel");
  });

  it("drops the question mark when nothing is left", () => {
    expect(without(new URL("http://host/?admin"), "admin")).toBe("/");
  });

  it("keeps the anchor when the view is not changing", () => {
    expect(without(new URL("http://host/?hub=a#travel"), "hub")).toBe("/#travel");
  });

  it("drops the anchor when it belonged to a page nobody is looking at", () => {
    expect(without(new URL("http://host/?admin#travel"), "admin", false)).toBe("/");
    expect(without(new URL("http://host/?admin&demo#travel"), "admin", false)).toBe("/?demo");
  });
});
