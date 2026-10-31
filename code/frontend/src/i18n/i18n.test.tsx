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
