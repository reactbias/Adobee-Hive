// How a hub's calibration reads to a person. This is the one number in the trust model that is easy to show
// backwards, and a backwards trust model is worse than none, so the reading lives here with its own tests.
//
// `error` is the hub's published rating minus what our people actually found, in tenths of a star.
//   error > 0  the hub promised more than people found  -> over-promised, the bad direction
//   error < 0  the hub promised less than people found  -> undersold what it offered, credit
//   error = 0  the published rating held exactly
// Lower is better. It is null, and the verdict is "unproven", until enough scored introductions exist to say.

/** Which of the four readings a hub's calibration gets. "unproven" is not zero and not bad: it is unknown. */
export type Reading = "unproven" | "over" | "under" | "exact";

export interface Calibration {
  reading: Reading;
  /** Whole stars, always positive; the reading carries the direction. 0 when unproven. */
  stars: number;
}

/** Turn a peer's raw calibration into what to say about it. Thin evidence stays unproven, never zero. */
export function readCalibration(error: number | null, verdict: string): Calibration {
  if (error === null || error === undefined || verdict === "unproven") return { reading: "unproven", stars: 0 };
  const stars = Math.abs(error) / 10;
  if (error > 0) return { reading: "over", stars };
  if (error < 0) return { reading: "under", stars };
  return { reading: "exact", stars };
}

/** One star to one decimal, in the page's language. 4 tenths reads as 0.4, not 0,4000. */
export const stars = (n: number, intl: string): string =>
  new Intl.NumberFormat(intl, { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(n);
