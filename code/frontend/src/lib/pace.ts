// How long each message in the group chat waits before it appears. People pause to think and type; agents here do
// too, a little faster, so a room can follow who is talking without the conversation arriving all at once.

/** first: the guest's own line. instant: a reply to a click. think: an agent deciding on a call. reply: a business
 * answering one. say: a line of text, timed by its length. */
export type Beat = "first" | "instant" | "think" | "reply" | "say";

const FIXED: Record<Exclude<Beat, "say">, number> = { first: 700, instant: 400, think: 1500, reply: 2300 };

/** Milliseconds of presence before a message with this beat appears. */
export function delayFor(beat: Beat, chars = 0): number {
  return beat === "say" ? Math.min(3600, Math.max(1600, 1000 + chars * 14)) : FIXED[beat];
}

/** Total playback time of a run of messages. */
export const playback = (beats: { beat: Beat; chars?: number }[]) =>
  beats.reduce((ms, b) => ms + delayFor(b.beat, b.chars), 0);
