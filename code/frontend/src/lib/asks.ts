// What this person asked before, kept in their own browser and nowhere else.
//
// The hub does log a search, but on purpose it cannot be read back to anybody: `hive.py` writes one row per
// search under `card_id = "*"` with no requester, no session and no query text, only the shape of the request
// (features, near, price, guests, matched). That is the privacy decision, and it means "see my past searches"
// is not a question the backend can answer even in principle — not until there is an identity to attach it to.
//
// So it is answered here. The text of an ask stays in this browser's localStorage, is never sent anywhere, and
// a person can drop all of it in one click. Storage being blocked or full is not an error: the list is then
// simply empty, as it is for a visitor who has asked nothing yet.

const KEY = "adobee-asks";

/** How many to keep. Enough to find this morning's request again, few enough not to become a profile. */
export const KEEP = 8;

function read(): string[] {
  try {
    const saved: unknown = JSON.parse(localStorage.getItem(KEY) ?? "[]");
    if (!Array.isArray(saved)) return [];
    return saved.filter((ask): ask is string => typeof ask === "string" && ask.trim().length > 0).slice(0, KEEP);
  } catch {
    return [];
  }
}

/** The asks this browser remembers, newest first. */
export const pastAsks = (): string[] => read();

/**
 * Remember an ask, newest first, and return the new list.
 *
 * The same request asked twice is one entry moved back to the front, not two: a list that fills up with
 * repeats of the last thing typed is not a history anybody can use. Case and surrounding space do not make a
 * different ask, but the text is kept as the person wrote it.
 */
export function rememberAsk(text: string): string[] {
  const ask = text.trim();
  if (!ask) return read();
  const same = ask.toLowerCase();
  const kept = [ask, ...read().filter((old) => old.trim().toLowerCase() !== same)].slice(0, KEEP);
  try {
    localStorage.setItem(KEY, JSON.stringify(kept));
  } catch {
    /* storage blocked or full: this visit keeps no history, which is not an error */
  }
  return kept;
}

/** Drop the lot. One click, no confirmation step, because nothing here is worth a dialog. */
export function forgetAsks(): void {
  try {
    localStorage.removeItem(KEY);
  } catch {
    /* nothing was stored, so nothing has to be removed */
  }
}
