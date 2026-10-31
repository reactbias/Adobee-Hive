import type { ReactNode, RefObject } from "react";

// The app is two screens, one per person: the traveller's (find and book) and the business's. The header switches
// between them by hash; App.tsx keeps both mounted so a booking survives a look at the other side.

export type ScreenId = "travel" | "business";
export const SCREENS: ScreenId[] = ["travel", "business"];

/** A light panel: an optional header, and a body that scrolls inside when its parent gives it a height. */
export function Frame({
  label,
  head,
  bodyRef,
  children,
}: {
  label: string;
  head?: ReactNode;
  bodyRef?: RefObject<HTMLDivElement>;
  children: ReactNode;
}) {
  return (
    <section className="frame" aria-label={label}>
      {head && <div className="frame-head">{head}</div>}
      <div className="frame-body" ref={bodyRef}>
        {children}
      </div>
    </section>
  );
}
