import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "../i18n";
import en from "../i18n/en";
import { pastAsks, rememberAsk } from "../lib/asks";
import PastAsks from "./PastAsks";

function draw(asks: string[], onAsk = vi.fn(), onForget = vi.fn()) {
  render(
    <I18nProvider>
      <PastAsks asks={asks} onAsk={onAsk} onForget={onForget} />
    </I18nProvider>,
  );
  return { onAsk, onForget };
}

describe("past searches", () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem("adobee-locale", "en");
  });

  it("draws nothing before the first ask, so a first visit carries no empty heading", () => {
    draw([]);
    expect(screen.queryByText(en["asks.title"])).not.toBeInTheDocument();
  });

  it("asks it again when a past ask is clicked", () => {
    const { onAsk } = draw(["a room in Basel"]);
    fireEvent.click(screen.getByRole("button", { name: en["asks.again"].replace("{ask}", "a room in Basel") }));
    expect(onAsk).toHaveBeenCalledWith("a room in Basel");
  });

  it("forgets the lot, in storage and on screen", () => {
    rememberAsk("a room in Basel");
    const { onForget } = draw(["a room in Basel"]);
    fireEvent.click(screen.getByRole("button", { name: en["asks.forget"] }));
    expect(pastAsks()).toEqual([]);
    expect(onForget).toHaveBeenCalled();
  });

  it("says where the list lives, because the hub does not have it", () => {
    draw(["a room in Basel"]);
    expect(screen.getByText(en["asks.only"])).toBeInTheDocument();
  });
});
