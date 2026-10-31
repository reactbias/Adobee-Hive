import type { Key } from "../i18n/en";

// The Hive gives its reasons in fixed English phrases, because agents read them as data. People read them here, in
// their own language: each phrase maps to a key, its values (features, names, dates) stay as the card wrote them.

type T = (key: Key, vars?: Record<string, string | number>) => string;

const PATTERNS: [RegExp, Key, string[]][] = [
  [/^mentions (.+)$/, "reason.mentions", ["words"]],
  [/^fits your mood: (.+)$/, "reason.mood", ["tags"]],
  [/^this month$/, "reason.this_month", []],
  [/^recent news$/, "reason.news", []],
  [/^coming up on (\S+)$/, "reason.coming", ["date"]],
  [/^no published price, ask for a quote$/, "reason.quote", []],
  [/^(\S+ [\d.,]+) per (.+) is over your budget of CHF ([\d.,]+)$/, "reason.over_budget", ["price", "per", "budget"]],
  [/^set aside for your mood: (.+)$/, "reason.mood_aside", ["tags"]],
  [/^signed facts expired on (\S+); the owner has to re-sign$/, "reason.expired", ["date"]],
  [/^missing (.+)$/, "reason.missing", ["features"]],
  [/^has (.+)$/, "reason.has", ["features"]],
  [/^takes no stay bookings$/, "reason.no_stays", []],
  [/^no room for (\d+) from (\S+) to (\S+)$/, "reason.no_room", ["guests", "from", "to"]],
  [/^(.+) free at CHF ([\d.,]+)\/night$/, "reason.free", ["unit", "price"]],
  [/^cheapest fit CHF ([\d.,]+) > budget CHF ([\d.,]+)$/, "reason.over_budget_stay", ["price", "budget"]],
  [/^(\d+) m from (.+)$/, "reason.distance", ["m", "near"]],
];

/** One of the Hive's reasons in the reader's language; a phrase this page does not know is shown as it came. */
export function reasonText(t: T, reason: string): string {
  for (const [re, key, names] of PATTERNS) {
    const m = re.exec(reason);
    if (m) return t(key, Object.fromEntries(names.map((n, i) => [n, m[i + 1]])));
  }
  return reason;
}
