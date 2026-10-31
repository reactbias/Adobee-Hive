import { describe, expect, it } from "vitest";

// jsdom does not apply the stylesheet, so these read it: a few rules a person would otherwise only catch by eye.
const css = Object.values(
  import.meta.glob<string>("./styles.css", { query: "?raw", import: "default", eager: true }),
)[0];
const rule = (selector: string) => {
  const at = css.indexOf(`${selector} {`);
  return at < 0 ? "" : css.slice(at, css.indexOf("}", at));
};

describe("styles", () => {
  it("keeps a Try example readable on hover, over the dark hover of every other button", () => {
    // button:hover:not(:disabled) paints buttons dark; an example has to win that with its own light background.
    const hover = rule(".example:hover:not(:disabled)");
    expect(hover).toMatch(/background:\s*var\(--paper-2\)/);
    expect(hover).toMatch(/color:\s*var\(--ink\)/);
  });

  it("shows a clamped Try example in full on hover and focus", () => {
    expect(rule(".brief .example:hover,\n.brief .example:focus-visible")).toMatch(/-webkit-line-clamp:\s*unset/);
  });

  // A phone in German: long labels must never make the page wider than the screen.
  it("lets a single-column chapter shrink to the screen, whatever its content", () => {
    expect(css).toMatch(/\.chapter-grid \{\s*grid-template-columns: minmax\(0, 1fr\);/);
  });

  it("keeps the search bar one line", () => {
    expect(rule(".search-top .composer.bar")).toMatch(/border-radius:\s*999px/);
    expect(rule(".search-top .composer.bar textarea")).toMatch(/white-space:\s*nowrap/);
  });

  it("wraps the composer's buttons, and their labels, on a narrow screen", () => {
    expect(rule(".composer-actions")).toMatch(/flex-wrap:\s*wrap/);
    expect(rule(".composer-actions button")).toMatch(/white-space:\s*normal/);
  });

  it("keeps only the status dot in a phone's header, so four languages fit beside it", () => {
    expect(css).toMatch(/@media \(max-width: 480px\) \{\s*\.nav-end \.status \{\s*font-size: 0;/);
  });
});
