import type { Booking, Card } from "../api";

// The pure parts of the agent's next steps after a booking, kept apart from the UI so they can be tested.

/** Pick the place whose signed card shares most features with what the guest asked for. */
export function pickNearby(places: Card[], wanted: string[]): { card: Card; shared?: string } | null {
  const ranked = places
    .map((card) => ({ card, shared: card.features.filter((f) => wanted.includes(f)) }))
    .sort((a, b) => b.shared.length - a.shared.length);
  return ranked[0] ? { card: ranked[0].card, shared: ranked[0].shared[0] } : null;
}

// RFC 5545 text: escape the separators, and never let a line break from card data start a new property.
const text = (s: string) => s.replace(/[\;,]/g, (c) => `\\${c}`).replace(/\r?\n|\r/g, "\\n");
const day = (iso: string) => iso.replace(/-/g, "");

/** An all-day calendar event for the stay, with the signed receipt in the note. */
export function icsEvent(booking: Booking, address: string | undefined, now: Date): string {
  const stamp = now.toISOString().replace(/[-:]/g, "").replace(/\.\d+/, "");
  return [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//Adobee Hive//Traveller agent//EN",
    "BEGIN:VEVENT",
    `UID:${text(booking.booking_id)}@adobee-hive`,
    `DTSTAMP:${stamp}`,
    `DTSTART;VALUE=DATE:${day(booking.check_in)}`,
    `DTEND;VALUE=DATE:${day(booking.check_out)}`,
    `SUMMARY:${text(`${booking.business}, ${booking.unit_name}`)}`,
    ...(address ? [`LOCATION:${text(address)}`] : []),
    `DESCRIPTION:${text(`${booking.booking_id}\nSigned receipt ${booking.receipt}`)}`,
    "END:VEVENT",
    "END:VCALENDAR",
  ].join("\r\n");
}
