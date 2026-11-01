import { describe, expect, it } from "vitest";
import { canonicalHash, joinHash, joinHubIn, namesScreen, screenFor, SCREENS } from "./Chapter";

// The screens are finding and offering, the two sides of every Card. They used to be called travel and
// business, which named two kinds of person rather than two things a Card does, and read wrongly on a hub
// carrying hairdressers and developers. The old names are still read, so a link already in the wild works.

describe("which screen a hash asks for", () => {
  it("is the two in the header, plus the network view beside them", () => {
    expect(SCREENS).toEqual(["find", "offer"]);
    expect(screenFor("#find")).toBe("find");
    expect(screenFor("#offer")).toBe("offer");
    expect(screenFor("#network")).toBe("network");
  });

  it("still reads the names the screens used to carry", () => {
    // Pasted into chats and slides before the rename; a jury may have one open.
    expect(screenFor("#travel")).toBe("find");
    expect(screenFor("#business")).toBe("offer");
  });

  it("opens on finding for an address that names no screen", () => {
    expect(screenFor("")).toBe("find");
    expect(screenFor("#")).toBe("find");
    expect(screenFor("#nothing-here")).toBe("find");
  });
});

describe("writing a hash the way the app writes it", () => {
  it("rewrites an old name, so a link copied back out carries the new one", () => {
    expect(canonicalHash("#travel")).toBe("#find");
    expect(canonicalHash("#business")).toBe("#offer");
  });

  it("leaves alone anything the app would have written itself", () => {
    // "" means there is nothing to rewrite, so the address is never touched for its own sake.
    expect(canonicalHash("#find")).toBe("");
    expect(canonicalHash("#offer")).toBe("");
    expect(canonicalHash("#network")).toBe("");
    expect(canonicalHash("")).toBe("");
    expect(canonicalHash("#nothing-here")).toBe("");
  });
});

describe("joining a Hive is a route too", () => {
  it("reads the hub out of the hash, and nothing else out of it", () => {
    expect(joinHubIn("#join/basel")).toBe("basel");
    expect(joinHubIn(joinHash("hive.example"))).toBe("hive.example");
    // Not a join hash: the bare word names no hub, so there is nothing to join.
    expect(joinHubIn("#join")).toBe("");
    expect(joinHubIn("#find")).toBe("");
    expect(joinHubIn("")).toBe("");
  });

  it("is not one of the screens, so returning to it does not fall through to the traveller's", () => {
    expect(namesScreen("#find")).toBe(true);
    expect(namesScreen("#offer")).toBe(true);
    expect(namesScreen("#network")).toBe(true);
    expect(namesScreen("#travel")).toBe(true);
    // An empty hash is where the Hive list sits, and a join hash is its own thing.
    expect(namesScreen("")).toBe(false);
    expect(namesScreen("#join/basel")).toBe(false);
  });

  it("opens on finding for a join hash, which the join view then outranks", () => {
    expect(screenFor("#join/basel")).toBe("find");
    expect(canonicalHash("#join/basel")).toBe("");
  });
});
