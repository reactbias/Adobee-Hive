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

  it("wraps a long search in the bar instead of hiding it off to the side", () => {
    expect(rule(".search-top .composer.bar")).toMatch(/border-radius:\s*24px/);
    expect(rule(".search-top .composer.bar")).toMatch(/align-items:\s*end/);
    expect(rule(".search-top .composer.bar textarea")).toMatch(/white-space:\s*pre-wrap/);
    expect(rule(".search-top .composer.bar textarea")).not.toMatch(/overflow-x:\s*auto/);
  });

  it("shows the search bar's Try examples as chips beside their label, not as loose text", () => {
    expect(rule(".search-top .examples")).toMatch(/display:\s*flex/);
    expect(rule(".search-top .examples .example")).toMatch(/border:\s*1px solid/);
    expect(rule(".search-top .examples .example")).toMatch(/border-radius:\s*999px/);
    expect(rule(".search-top .examples .example:hover:not(:disabled)")).toMatch(/border-color:\s*var\(--clay\)/);
  });

  it("keeps the count and the Details toggle in view beside a long question", () => {
    expect(rule(".result-head")).toMatch(/min-width:\s*0/);
  });

  it("rings the search bar while you type in it", () => {
    expect(rule(".search-top .composer.bar:focus-within")).toMatch(/border-color:\s*var\(--clay\)/);
  });

  it("wraps the composer's buttons, and their labels, on a narrow screen", () => {
    expect(rule(".composer-actions")).toMatch(/flex-wrap:\s*wrap/);
    expect(rule(".composer-actions button")).toMatch(/white-space:\s*normal/);
  });

  it("keeps only the status dot in a phone's header, so four languages fit beside it", () => {
    expect(css).toMatch(/@media \(max-width: 480px\) \{\s*\.nav-end \.status \{\s*font-size: 0;/);
  });
});
