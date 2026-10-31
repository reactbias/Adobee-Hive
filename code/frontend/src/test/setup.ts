import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "/");
});

// jsdom has no layout, so no scrolling API; the group chat scrolls itself to the newest message.
Element.prototype.scrollTo ??= function scrollTo() {};

// Nor media queries; the footer bee asks whether the person prefers reduced motion.
window.matchMedia ??= ((query: string) =>
  ({ matches: false, media: query }) as MediaQueryList) as typeof window.matchMedia;
