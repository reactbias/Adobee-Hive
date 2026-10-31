import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nProvider, useI18n } from ".";
import de from "./de";
import en, { type Key } from "./en";
import fr from "./fr";
import it_ from "./it";

function Says({ k, vars }: { k: string; vars?: Record<string, string> }) {
  const { t } = useI18n();
  return <p>{t(k as Key, vars)}</p>;
}

describe("i18n", () => {
  it("fills placeholders", () => {
    render(
      <I18nProvider>
        <Says k="agent.review.stored" vars={{ id: "rv_1" }} />
      </I18nProvider>,
    );
    expect(screen.getByText(en["agent.review.stored"].replace("{id}", "rv_1"))).toBeInTheDocument();
  });

  it("shows the key, not a crash, for a code the backend added before the strings", () => {
    render(
      <I18nProvider>
        <Says k="broken.something_new" vars={{ price: "1" }} />
      </I18nProvider>,
    );
    expect(screen.getByText("broken.something_new")).toBeInTheDocument();
  });

  it("keeps every placeholder in every language", () => {
    const holes = (s: string) => (s.match(/\{\w+\}/g) ?? []).sort().join();
    for (const dict of [de, fr, it_]) {
      for (const key of Object.keys(en) as Key[]) expect([key, holes(dict[key])]).toEqual([key, holes(en[key])]);
    }
  });

  it("writes Swiss German: ss, never ß", () => {
    expect(Object.values(de).filter((s) => s.includes("ß"))).toEqual([]);
  });
});

// Every change ships in all four languages. These guard what the type check can't see.
describe("all four languages", () => {
  const others = { de, fr, it: it_ };

  it("have exactly the same keys, none empty", () => {
    const keys = Object.keys(en).sort();
    for (const [name, dict] of Object.entries(others)) {
      expect([name, Object.keys(dict).sort()]).toEqual([name, keys]);
      expect([name, Object.entries(dict).filter(([, v]) => !v.trim())]).toEqual([name, []]);
    }
  });

  it("are translated, not English copied over", () => {
    // Short labels, names and codes may match English in every language; longer text may not.
    const copied = Object.entries(others).flatMap(([name, dict]) =>
      (Object.keys(en) as Key[])
        .filter((k) => dict[k] === en[k] && en[k].length >= 14 && !SAME_EVERYWHERE.has(k))
        .map((k) => `${name}: ${k}`),
    );
    expect(copied).toEqual([]);
  });
});

// No dead strings: every key is used by the app, by name or under a prefix the code fills in (`guard.${code}`).
describe("every string", () => {
  const code = Object.values(
    import.meta.glob<string>(["../**/*.{ts,tsx}", "!../**/*.test.{ts,tsx}", "!../i18n/*.ts"], {
      query: "?raw",
      import: "default",
      eager: true,
    }),
  ).join("\n");
  const prefixes = [...code.matchAll(/`([a-z]+(?:\.[a-z]+)*\.)\$\{/g)].map((m) => m[1]);

  it("is used somewhere", () => {
    const unused = (Object.keys(en) as Key[]).filter(
      (k) => !code.includes(`"${k}"`) && !prefixes.some((p) => k.startsWith(p)),
    );
    expect(unused).toEqual([]);
  });
});

// Keys whose text is a name, not language.
const SAME_EVERYWHERE = new Set<Key>(["footer.line"]);
