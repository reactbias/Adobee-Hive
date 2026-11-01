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
    expect(hover).toMatch(/background:\s*var\(--surface-2\)/);
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
  it("lets the business screen collapse to one column, whatever its content", () => {
    expect(css).toMatch(/\.owner-grid \{\s*grid-template-columns: minmax\(0, 1fr\);/);
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
    expect(rule(".search-top .examples .example:hover:not(:disabled)")).toMatch(/border-color:\s*var\(--accent\)/);
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
    expect(rule(".search-top .composer.bar:focus-within")).toMatch(/border-color:\s*var\(--accent\)/);
  });

  it("wraps the composer's buttons, and their labels, on a narrow screen", () => {
    expect(rule(".composer-actions")).toMatch(/flex-wrap:\s*wrap/);
    expect(rule(".composer-actions button")).toMatch(/white-space:\s*normal/);
  });

  // Honey on white: one accent, named for what it is, and a dark stage that lifts it rather than a second accent.
  it("has honey as its one accent", () => {
    expect(rule(":root")).toMatch(/--accent:\s*#d99a1e/);
    expect(rule(":root")).toMatch(/--accent-bright:\s*#f2b63c/);
    expect(rule(":root")).toMatch(/--stage:\s*#15171c/);
  });

  it("keeps the pinned search bar on white, so the results read under it", () => {
    expect(rule(".search-top")).toMatch(/background:[^;]*var\(--bg\)/);
  });

  // The phone rule this used to pin (`.nav-end .status { font-size: 0 }`) hid the status text so that
  // four language buttons still fitted beside it. The backend-status component moved the status out of
  // the header into a bar of its own below it, so there is no longer any status text in the header to
  // hide — measured in Chrome at 360px in German, the widest case, the header has 127px to spare. What
  // still has to hold is the two rules that give the header that room, so those are what is pinned now.
  // Dark mode redefines the tokens; a colour written as a literal outside :root cannot follow. These pin the
  // ones that would otherwise paint white on white the moment --ink stops being nearly black.
  it("paints a primary action with a token, so the label follows the surface under it", () => {
    const primary = rule("button,\n.btn");
    expect(primary).toMatch(/background:\s*var\(--ink\)/);
    expect(primary).toMatch(/color:\s*var\(--on-ink\)/);
    expect(rule("button:hover:not(:disabled),\n.btn:hover")).toMatch(/background:\s*var\(--ink-hover\)/);
  });

  it("frosts the sticky header over whatever the page is, rather than over white", () => {
    expect(rule(".nav")).toMatch(/background:\s*var\(--bg-frosted\)/);
  });

  it("has one focus ring, named, rather than the same honey written out at each control", () => {
    expect(rule("input:focus,\ntextarea:focus,\nselect:focus")).toMatch(/box-shadow:[^;]*var\(--ring\)/);
    expect(rule(".search-top .composer.bar:focus-within")).toMatch(/var\(--ring-wide\)/);
    expect(rule(".composer textarea:focus")).toMatch(/var\(--ring-wide\)/);
  });

  it("writes no opaque white outside the tokens, where a dark page could not override it", () => {
    // Translucent white is legitimate: it is the inset highlight on the dark agent stage, which stays dark in
    // both schemes. An opaque white is a page surface, and a page surface has to be a token.
    const declarations = css.replace(/\/\*[\s\S]*?\*\//g, "");
    const body = declarations.slice(declarations.indexOf("}", declarations.indexOf(":root {")) + 1);
    const opaqueWhite = body.match(/:\s*(?:#fff\b|#ffffff\b|white\b)/gi) ?? [];
    expect(opaqueWhite).toEqual([]);
  });

  // Dark mode. The page becomes the agent stage, guarded the way the pitch deck guards its own dark block.
  it("has a dark scheme that an explicit light choice still wins over", () => {
    expect(css).toMatch(/@media \(prefers-color-scheme: dark\) \{\s*:root:not\(\[data-theme="light"\]\) \{/);
  });

  it("redefines the page in the dark block, not only the text on it", () => {
    const dark = css.slice(css.indexOf("@media (prefers-color-scheme: dark)"));
    const block = dark.slice(0, dark.indexOf("\n  }"));
    // A half-converted scheme is worse than none: these are the tokens every surface and label reads from.
    for (const token of ["--bg", "--surface", "--surface-2", "--sunk", "--ink", "--ink-2", "--ink-3", "--line"])
      expect([token, block.includes(`${token}:`)]).toEqual([token, true]);
    // The ones that would otherwise paint white on white, or cast a slate shadow onto a black page.
    for (const token of ["--on-ink", "--ink-hover", "--bg-frosted", "--lift"])
      expect([token, block.includes(`${token}:`)]).toEqual([token, true]);
    // The stage lifts rather than staying put, or the agents dissolve into the page behind them. The value
    // now lives once in the palette and the block maps it, so both are checked.
    expect(rule(":root")).toMatch(/--dk-stage:\s*#1b1f27/);
    expect(block).toMatch(/--stage:\s*var\(--dk-stage\)/);
  });

  it("switches the one dark palette on from the OS and from an explicit choice, identically", () => {
    // Two rules, one palette. If they ever drift, a reader who picks dark gets a different page from a reader
    // whose laptop is dark, which is the bug this shape exists to make impossible.
    const mapping = (from: string) => {
      const at = css.indexOf(from);
      const body = css.slice(at, css.indexOf("\n}", at));
      return (body.match(/--[\w-]+:\s*var\(--dk-[\w-]+\);/g) ?? []).join("\n");
    };
    const fromOs = mapping("@media (prefers-color-scheme: dark) {");
    const chosen = mapping(':root[data-theme="dark"] {');
    expect(chosen).toBe(fromOs);
    expect(chosen.split("\n").length).toBeGreaterThan(15);
    expect(rule(':root[data-theme="dark"]')).toMatch(/color-scheme:\s*dark/);
  });

  it("paints the page from html as well as body, so a dark OS leaves no white band", () => {
    // The overscroll area above and below the document is painted from html.
    expect(rule("html")).toMatch(/background:\s*var\(--bg\)/);
    expect(rule("body")).toMatch(/background:\s*var\(--bg\)/);
  });

  it("tells the browser which scheme it is in, so native controls and scrollbars follow", () => {
    expect(rule(":root")).toMatch(/color-scheme:\s*light/);
    const dark = css.slice(css.indexOf("@media (prefers-color-scheme: dark)"));
    expect(dark.slice(0, dark.indexOf("\n  }"))).toMatch(/color-scheme:\s*dark/);
  });

  it("gives every footer control a thumb-sized target on a touch screen, as the brand promises", () => {
    // Measured at 360px before this: the two Hive controls were 32px tall and the bee 15px, against
    // BRAND.md's "on touch screens every control has a 44 px target".
    const coarse = css.slice(css.lastIndexOf("@media (pointer: coarse) {"));
    expect(coarse).toMatch(/\.footer-hive a\.nav-hub,[\s\S]*?min-height:\s*44px/);
    expect(coarse).toMatch(/\.b6-perch \{[\s\S]*?min-height:\s*44px/);
    // The scheme buttons joined the same rule rather than growing one of their own.
    expect(coarse).toMatch(/\.themes button,/);
    // It has to come after the rules that pin them to 32px, or it loses on source order.
    expect(css.lastIndexOf("@media (pointer: coarse) {")).toBeGreaterThan(css.indexOf(".footer-hive a.nav-hub {"));
  });

  it("gives the phone header room: the chapters take their own row and the language buttons shrink", () => {
    expect(css).toMatch(
      /@media \(max-width: 900px\) \{[\s\S]*?\.nav-links \{[\s\S]*?grid-column: 1 \/ -1;[\s\S]*?overflow-x: auto;/,
    );
    expect(css).toMatch(/@media \(max-width: 480px\) \{\s*\.nav-end \.locales button \{\s*min-width: 34px;/);
  });
});
