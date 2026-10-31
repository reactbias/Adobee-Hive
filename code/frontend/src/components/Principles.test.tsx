import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { I18nProvider } from "../i18n";
import de from "../i18n/de";
import en from "../i18n/en";
import Principles from "./Principles";

// The four promises carry the brand's names, in the brand's order, in every language (BRAND.md).

describe("the principles strip", () => {
  it("names the four promises in order, each with one line", () => {
    localStorage.setItem("adobee-locale", "en");
    render(
      <I18nProvider>
        <Principles />
      </I18nProvider>,
    );
    const strip = screen.getByRole("list", { name: en["principles.label"] });
    const items = within(strip).getAllByRole("listitem");
    expect(items.map((li) => within(li).getByRole("heading").textContent)).toEqual([
      "Signed facts",
      "Open ranking",
      "Proof of stay",
      "Your yes",
    ]);
    expect(within(items[3]).getByText(en["principles.yes.body"])).toBeInTheDocument();
  });

  it("keeps the brand's German names", () => {
    localStorage.setItem("adobee-locale", "de");
    render(
      <I18nProvider>
        <Principles />
      </I18nProvider>,
    );
    expect(screen.getByRole("heading", { name: de["principles.signed.title"] })).toHaveTextContent("Signierte Fakten");
    expect(screen.getByRole("heading", { name: "Ihr Ja" })).toBeInTheDocument();
  });
});
