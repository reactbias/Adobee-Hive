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
