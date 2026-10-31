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
});
