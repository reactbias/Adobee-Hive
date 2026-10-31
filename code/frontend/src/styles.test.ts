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

  it("keeps a result card's name readable on hover, over the dark hover of every other button", () => {
    // all: unset loses to button:hover:not(:disabled) on specificity, so the name needs its own hover rule.
    expect(rule(".card-row h3 button:hover:not(:disabled)")).toMatch(/background:\s*none/);
  });

  it("shows a clamped Try example in full on hover and focus", () => {
    expect(rule(".brief .example:hover,\n.brief .example:focus-visible")).toMatch(/-webkit-line-clamp:\s*unset/);
  });

  // A phone in German: long labels must never make the page wider than the screen.
  it("lets a single-column chapter shrink to the screen, whatever its content", () => {
    expect(css).toMatch(/\.chapter-grid \{\s*grid-template-columns: minmax\(0, 1fr\);/);
  });

  it("keeps the search bar on screen, and wraps a long request inside it", () => {
    expect(rule(".search-top")).toMatch(/position:\s*sticky/);
    expect(rule(".search-top")).toMatch(/top:\s*var\(--nav-h\)/);
    expect(rule(".search-top .composer.bar")).toMatch(/border-radius:\s*24px/);
    expect(rule(".search-top .composer.bar textarea")).toMatch(/white-space:\s*pre-wrap/);
    expect(rule(".search-top .composer.bar textarea")).toMatch(/width:\s*100%/);
    expect(rule(".search-top .composer.bar textarea")).not.toMatch(/overflow-x:\s*auto/);
  });

  it("shows the search bar's Try examples as chips beside their label, not as loose text", () => {
    expect(rule(".search-top .examples")).toMatch(/display:\s*flex/);
    expect(rule(".search-top .examples .example")).toMatch(/border:\s*1px solid/);
    expect(rule(".search-top .examples .example")).toMatch(/border-radius:\s*999px/);
    expect(rule(".search-top .examples .example:hover:not(:disabled)")).toMatch(/border-color:\s*var\(--clay\)/);
  });

  it("keeps the question in full and locks the count and Details on that row", () => {
    // A long question wraps instead of being cut off, and the count and Details stay beside it.
    expect(rule(".result-head")).toMatch(/min-width:\s*0/);
    expect(rule(".result-head")).toMatch(/flex-wrap:\s*nowrap/);
    expect(rule(".result-query")).toMatch(/white-space:\s*normal/);
    expect(rule(".result-query")).not.toMatch(/text-overflow/);
    expect(rule(".result-actions")).toMatch(/flex:\s*none/);
    expect(css).toMatch(
      /@media \(max-width: 600px\) \{\s*\.result-head \{\s*flex-wrap:\s*wrap;\s*\}\s*\.result-query \{\s*flex-basis:\s*100%;/,
    );
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
