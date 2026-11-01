import type { ReactNode, RefObject } from "react";

// The app is two screens, and they are not two kinds of person: they are the two sides of every Card, finding
// and offering. A hub carrying hairdressers and developers has no travellers in it, and the entity that offers a
// room this week is looking for a designer the next. The header switches between them by hash; App.tsx keeps
// both mounted so a booking survives a look at the other side.

export type ScreenId = "find" | "offer" | "network";
/** The two screens in the header. The network view is a third, reached from the footer. */
export const SCREENS: ScreenId[] = ["find", "offer"];

/**
 * The hash names these screens used to carry, read and never written.
 *
 * `#travel` and `#business` went into chats, slides and the readme before the screens were renamed, so a link
 * someone already has open still opens the screen it names. Everything the app emits uses the name beside it,
 * and `canonicalHash` rewrites an old one in the address bar so a URL copied back out carries the new name.
 */
const RENAMED: Record<string, ScreenId> = { travel: "find", business: "offer" };

/** The screen a hash asks for, old names included. Anything the app does not serve opens on finding. */
export function screenFor(hash: string): ScreenId {
  const name = hash.replace(/^#/, "");
  const screen = RENAMED[name] ?? name;
  return screen === "offer" || screen === "network" ? screen : "find";
}

/** The same hash as the app would write it, or "" when it is already written that way. */
export function canonicalHash(hash: string): string {
  const renamed = RENAMED[hash.replace(/^#/, "")];
  return renamed ? `#${renamed}` : "";
}

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
