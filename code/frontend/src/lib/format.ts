// Display helpers shared by the pages. Dates arrive as ISO days (YYYY-MM-DD); `intl` is a tag like "de-CH".

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;
const asDate = (iso: unknown) => (ISO_DAY.test(String(iso)) ? new Date(`${iso}T00:00:00Z`) : null);
const dayFormat = (intl: string) =>
  new Intl.DateTimeFormat(intl, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });

export function day(iso: unknown, intl: string): string {
  const d = asDate(iso);
  return d ? dayFormat(intl).format(d) : String(iso ?? "");
}

// "13–15 Nov 2026", collapsing the shared month and year the way each locale does.
export function stay(from: unknown, to: unknown, intl: string): string {
  const a = asDate(from);
  const b = asDate(to);
  if (!a || !b) return `${from ?? ""} – ${to ?? ""}`;
  return dayFormat(intl).formatRange(a, b);
}

export function nights(from: unknown, to: unknown): number {
  const a = asDate(from);
  const b = asDate(to);
  return a && b ? Math.round((b.getTime() - a.getTime()) / 86_400_000) : 0;
}

export const chf = (n: unknown, intl: string) =>
  new Intl.NumberFormat(intl, { style: "currency", currency: "CHF", maximumFractionDigits: 0 }).format(Number(n));

export const metres = (m: unknown, intl: string) => {
  const n = Number(m);
  const unit = n >= 1000 ? "kilometer" : "meter";
  return new Intl.NumberFormat(intl, { style: "unit", unit, maximumFractionDigits: 1 }).format(
    n >= 1000 ? n / 1000 : n,
  );
};

// A full ISO timestamp (a published_at, a last-checked) as a date in the reader's language. The time of day is
// noise in these tables, so it is dropped rather than formatted.
export const dayOf = (iso: unknown, intl: string) => day(String(iso ?? "").slice(0, 10), intl);

export const capitalise = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

export const money = (n: unknown, currency: string, intl: string) =>
  new Intl.NumberFormat(intl, { style: "currency", currency, maximumFractionDigits: 0 }).format(Number(n));

/**
 * How long ago an ISO 8601 moment was, in the page's language: "2 minutes ago", "vor 2 Minuten", "yesterday".
 *
 * `Intl.RelativeTimeFormat` does the words, so there is nothing to translate and nothing to pluralise by hand.
 * Returns "" for a missing or unparsable stamp, so a caller renders its own "never" rather than a wrong time.
 */
export function since(iso: unknown, intl: string, now: Date = new Date()): string {
  const then = iso ? new Date(String(iso)) : null;
  if (!then || Number.isNaN(then.getTime())) return "";
  const seconds = Math.round((then.getTime() - now.getTime()) / 1000);
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ["second", 60],
    ["minute", 60],
    ["hour", 24],
    ["day", 7],
    ["week", 4.35],
    ["month", 12],
  ];
  const format = new Intl.RelativeTimeFormat(intl, { numeric: "auto" });
  let value = seconds;
  for (const [unit, per] of units) {
    if (Math.abs(value) < per) return format.format(value, unit);
    value = Math.round(value / per);
  }
  return format.format(value, "year");
}

/** The exact moment, for a `title` on a relative time. "" when there is nothing to show. */
export const moment = (iso: unknown, intl: string): string => {
  const then = iso ? new Date(String(iso)) : null;
  if (!then || Number.isNaN(then.getTime())) return "";
  return new Intl.DateTimeFormat(intl, { dateStyle: "medium", timeStyle: "short" }).format(then);
};
