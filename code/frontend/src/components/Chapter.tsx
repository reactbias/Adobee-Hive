import type { ReactNode, RefObject } from "react";

// The app's main screens are finding and offering, the two sides of every Card, not two kinds of person: a hub
// carrying hairdressers and developers has no travellers in it, and the entity that offers a room this week is
// looking for a designer the next. Hiring sits between them. The header switches by hash; App.tsx keeps them all
// mounted so a booking survives a look at another screen.

export type ScreenId = "find" | "hr" | "offer" | "network";
/** The traveller and HR screens share the journey header; the network view is reached from the footer. */
export const SCREENS: ScreenId[] = ["find", "hr", "offer"];

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
  return screen === "hr" || screen === "offer" || screen === "network" ? screen : "find";
}

/**
 * Joining a Hive is a route too: `#join/<hub>`.
 *
 * It was React state and nothing else, so the browser's own back button and a phone's back gesture left the
 * app entirely instead of returning to the Hive list, and a header link could not get past it. The hub rides
 * in the hash so a reload comes back to the same application rather than to a blank screen. Nothing that has
 * been *typed* is in the address: an application starts over on a reload, and a link promising to restore a
 * half-filled form would be a lie about what it restores.
 */
const JOIN = "join";

/** The hub an address asks to join, or "" when it asks for something else. */
export function joinHubIn(hash: string): string {
  const [name, ...rest] = hash.replace(/^#/, "").split("/");
  return name === JOIN && rest.length ? decodeURIComponent(rest.join("/")) : "";
}

/** The address for joining one Hive. */
export const joinHash = (hub: string): string => `#${JOIN}/${encodeURIComponent(hub)}`;

/**
 * True when the hash names one of the app's screens outright.
 *
 * An empty hash does not: it is where the finder sits, so coming back to it from `#join/...` has to leave the
 * Hive list on screen rather than falling through to the traveller's.
 */
export function namesScreen(hash: string): boolean {
  const name = hash.replace(/^#/, "");
  if (!name) return false;
  const screen = RENAMED[name] ?? name;
  return screen === "find" || screen === "hr" || screen === "offer" || screen === "network";
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
