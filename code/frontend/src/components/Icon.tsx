// Adobee Hive's own icon set: hairline strokes on a 24-px grid, drawn around the hexagon of the logo.
// Shapes are hand-drawn here rather than taken from an icon library, so they share one geometry.

const HEX = "M12 2.8 19.8 7.3v9.4L12 21.2 4.2 16.7V7.3Z";

const PATHS = {
  // A signed card: the cell with a check, the check drawn last so it can animate.
  seal: [HEX, "M8.6 12.2l2.3 2.3 4.6-4.8"],
  // Ranked in the open: three bars of different height inside the cell.
  rank: [HEX, "M9 15v-3M12 15V9M15 15v-1.6"],
  // Proof of booking: a receipt with a torn foot.
  receipt: ["M7 3.5h10v16.5l-1.7-1.2-1.6 1.2-1.7-1.2-1.6 1.2-1.7-1.2L7 20Z", "M9.5 8h5M9.5 11h5M9.5 14h3"],
  // Your yes: an open hand of agreement reduced to a check in a circle.
  yes: ["M12 3.5a8.5 8.5 0 1 1 0 17 8.5 8.5 0 0 1 0-17Z", "M8.5 12.3l2.4 2.4 4.6-5"],
  // Missed demand: an empty cell with a dashed edge.
  missed: ["M12 2.8 19.8 7.3v9.4L12 21.2 4.2 16.7V7.3Z"],
  // The owner's key.
  key: ["M14.5 4a5 5 0 1 1-4.3 7.6L4 17.8V20h2.6v-1.8h1.8v-1.8h1.8l1.6-1.6A5 5 0 0 1 14.5 4Z", "M16 8.2h.01"],
  // Discover: a cluster of three cells.
  hive: [
    "M8.2 4.6l3 1.7v3.5l-3 1.7-3-1.7V6.3Z",
    "M15.8 4.6l3 1.7v3.5l-3 1.7-3-1.7V6.3Z",
    "M12 11.2l3 1.7v3.5l-3 1.7-3-1.7v-3.5Z",
  ],
  // Availability: a calendar leaf.
  calendar: ["M5 6.5h14V19H5Z", "M5 10h14M9 4v4M15 4v4"],
  // No paid placement: a coin, struck through.
  coin: [
    "M12 4a8 8 0 1 1 0 16 8 8 0 0 1 0-16Z",
    "M9.5 9.5c.4-.9 1.3-1.4 2.5-1.4 1.6 0 2.5.8 2.5 1.9 0 2.6-5 1.4-5 4 0 1.1 1 1.9 2.5 1.9 1.2 0 2.1-.5 2.5-1.4M12 6.5v1.6M12 15.9v1.6",
    "M4.5 19.5l15-15",
  ],
  // No profiling: an eye, closed.
  eyeOff: [
    "M3 12c2.2-3.6 5.4-5.5 9-5.5s6.8 1.9 9 5.5c-2.2 3.6-5.4 5.5-9 5.5S5.2 15.6 3 12Z",
    "M12 9.5a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5Z",
    "M4.5 19.5l15-15",
  ],
  // Data, never instructions: a quotation mark in brackets.
  quote: [
    "M8 5H5.5v14H8M16 5h2.5v14H16",
    "M10 10.5c0-1 .6-1.6 1.5-1.8M13 10.5c0-1 .6-1.6 1.5-1.8M10 10.5v2h1.5v-2ZM13 10.5v2h1.5v-2Z",
  ],
  arrow: ["M5 12h14M13 6l6 6-6 6"],
} as const;

export type IconName = keyof typeof PATHS;

export default function Icon({
  name,
  size = 20,
  className = "",
}: {
  name: IconName;
  size?: number;
  className?: string;
}) {
  return (
    <svg
      className={`icon icon-${name} ${className}`}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.4}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      {PATHS[name].map((d, i) => (
        <path key={i} d={d} strokeDasharray={name === "missed" ? "2.2 2.6" : undefined} />
      ))}
    </svg>
  );
}
