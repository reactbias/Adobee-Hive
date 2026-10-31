import { describe, expect, it } from "vitest";
import { delayFor, playback, type Beat } from "./pace";

// The offline planner's usual run: the guest, the ack, three MCP calls and answers, the critic's challenge, your
// agent's answer and the critic's verdict, the verifier, the agreement, the agent's reply.
const OFFLINE_RUN: { beat: Beat; chars?: number }[] = [
  { beat: "first" },
  { beat: "say", chars: 56 },
  { beat: "think" },
  { beat: "reply" },
  { beat: "think" },
  { beat: "reply" },
  { beat: "think" },
  { beat: "reply" },
  { beat: "think" },
  { beat: "say", chars: 40 },
  { beat: "say", chars: 14 },
  { beat: "think" },
  { beat: "say", chars: 20 },
  { beat: "say", chars: 260 },
];

describe("pace", () => {
  it("lands the guest's own line at once", () => {
    expect(delayFor("first")).toBeLessThan(1000);
    expect(delayFor("instant")).toBeLessThan(delayFor("first"));
  });

  it("gives longer lines longer to type, within a natural range", () => {
    expect(delayFor("say", 200)).toBeGreaterThan(delayFor("say", 20));
    expect(delayFor("say", 0)).toBeGreaterThanOrEqual(1600);
    expect(delayFor("say", 10_000)).toBeLessThanOrEqual(3600);
  });

  it("lets an agent think before it calls a tool, and a business take a beat to answer", () => {
    expect(delayFor("think")).toBeGreaterThan(1000);
    expect(delayFor("reply")).toBeGreaterThan(delayFor("think"));
  });

  it("reaches the approval question in the demo beat: natural, a little faster than people", () => {
    const ms = playback(OFFLINE_RUN);
    expect(ms).toBeGreaterThan(18_000);
    expect(ms).toBeLessThan(30_000);
  });
});
