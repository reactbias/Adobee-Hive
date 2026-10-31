// Introductions as a person meets them: what connecting will take before the click, who is asking, when the
// moment to score has passed, and what a score did.
//
// The button has to tell the truth before the click. A "Connect" that silently queues a request teaches people the
// product lies to them, so a `confirm` entry is an "Ask to connect" that says it will wait.

import type { Connection, ScoreOutcome } from "../api";
import type { Key } from "../i18n/en";

/** `now` opens at once, `ask` waits for the owner's yes, null means nothing may be asked for. */
export type ConnectMode = "now" | "ask" | null;

// The hub's own default when an entry says nothing (hub.py): an introduction to a person is theirs to grant.
const CONSENT_FIRST_KINDS = new Set(["person"]);

export function connectMode(sharing: string | undefined, kind: string): ConnectMode {
  const flag = sharing || (CONSENT_FIRST_KINDS.has(kind) ? "confirm" : "public");
  if (flag === "public") return "now";
  if (flag === "confirm") return "ask";
  return null;
}

const REQUESTER_KEY = "adobee-requester";
const NAMES_KEY = "adobee-introduced";

/** Who is asking, as this hub will know them: one id per browser, so its introductions can be found again. */
export function requesterId(): string {
  try {
    const saved = localStorage.getItem(REQUESTER_KEY);
    if (saved) return saved;
  } catch {
    /* storage blocked: a fresh id for this visit */
  }
  const bytes = crypto.getRandomValues(new Uint8Array(4));
  const id = `traveller-${[...bytes].map((b) => b.toString(16).padStart(2, "0")).join("")}`;
  try {
    localStorage.setItem(REQUESTER_KEY, id);
  } catch {
    /* the id lasts as long as this visit */
  }
  return id;
}

function names(): Record<string, string> {
  try {
    return JSON.parse(localStorage.getItem(NAMES_KEY) ?? "{}") as Record<string, string>;
  } catch {
    return {};
  }
}

/** A connection names its target by id; keep the name the person saw, so "How did it go with X?" says it. */
export function remember(entityId: string, name: string) {
  try {
    localStorage.setItem(NAMES_KEY, JSON.stringify({ ...names(), [entityId]: name }));
  } catch {
    /* the prompt falls back to the id */
  }
}

export const nameFor = (entityId: string): string => names()[entityId] ?? entityId;

/** Past its deadline, an introduction can no longer be scored, and the page stops asking. */
export function isStale(connection: Connection, now = new Date()): boolean {
  if (connection.state === "stale") return true;
  return Boolean(connection.stale_at && new Date(connection.stale_at) < now);
}

export type ScoreSays =
  | { key: Extract<Key, "score.done">; hub: string; promised: number; found: number }
  | { key: Extract<Key, "score.exact">; hub: string }
  | { key: Extract<Key, "score.thanks"> };

/** The one moment a person sees their feedback move something: what the hub promised, and what they found. */
export function scoreSays(outcome: ScoreOutcome): ScoreSays {
  const { connection, hub } = outcome;
  const promised = connection.published_rating_stars;
  const found = connection.rating_stars;
  if (!hub || outcome.gap === undefined || promised === null || found === null) return { key: "score.thanks" };
  if (outcome.gap === 0) return { key: "score.exact", hub };
  return { key: "score.done", hub, promised, found };
}

/** One contact channel: published, gated behind a yes, or not provided. */
export type ContactRow = { channel: string; value: string; state: "shown" | "onRequest" | "none" };

/**
 * A channel with a value is published. An empty one is "available on request" when its owner gated it and "not
 * provided" otherwise. A channel the owner keeps to themselves is absent from the card and is not hinted at.
 */
export function contactRows(
  contact: Record<string, string> | undefined,
  sharing: Record<string, string> | undefined,
): ContactRow[] {
  return Object.entries(contact ?? {}).map(([channel, value]) => ({
    channel,
    value,
    state: value ? "shown" : sharing?.[channel] === "confirm" ? "onRequest" : "none",
  }));
}
