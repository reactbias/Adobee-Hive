import { describe, expect, it } from "vitest";

// No user-facing text in a component: everything a person reads goes through t(), so it exists in all four
// languages. This scans the JSX for text nodes and for text in attributes people read or hear.
const SOURCES = import.meta.glob<string>(["../**/*.tsx", "!../**/*.test.tsx"], {
  query: "?raw",
  import: "default",
  eager: true,
});

// Text that is not language: symbols, the brand, and markers like "B6".
const ALLOWED = /^(?:[^\p{L}]*|Adobee Hive|B6|MCP|CHF|JSON)$/u;

function hardcoded(source: string): string[] {
  const found: string[] = [];
  const code = source.replace(/\/\*[\s\S]*?\*\/|\{\/\*[\s\S]*?\*\/\}|^\s*\/\/.*$/gm, "");
  for (const m of code.matchAll(/>([^<>{}]*?)</g)) {
    const text = m[1].trim();
    if (text && /\p{L}{2,}/u.test(text) && !ALLOWED.test(text) && !/[=;()&|]/.test(text)) found.push(text);
  }
  for (const m of code.matchAll(/\b(?:placeholder|title|alt|aria-label|label)="([^"]*)"/g)) {
    if (/\p{L}{2,}/u.test(m[1]) && !ALLOWED.test(m[1])) found.push(m[1]);
  }
  return found;
}

describe("components", () => {
  it("are all scanned", () => {
    expect(Object.keys(SOURCES).length).toBeGreaterThan(5);
  });

  for (const [file, source] of Object.entries(SOURCES)) {
    it(`${file.replace("../", "src/")} has no hard-coded text`, () => {
      expect(hardcoded(source)).toEqual([]);
    });
  }
});

describe("the scan itself", () => {
  it("catches text nodes and readable attributes", () => {
    const sample = `<div><h1>Book now</h1><input placeholder="Your name" /><img alt="Logo" /></div>`;
    expect(hardcoded(sample)).toEqual(["Book now", "Your name", "Logo"]);
  });

  it("lets t() calls, symbols and the brand through", () => {
    const sample = `<p>{t("agent.send")}</p><span>·</span><b>Adobee Hive</b><i>★</i><x aria-label={t("k")} />`;
    expect(hardcoded(sample)).toEqual([]);
  });
});
