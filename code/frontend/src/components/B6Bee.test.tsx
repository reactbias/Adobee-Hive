import { act, render } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "../i18n";
import { THEME_EVENT } from "../lib/theme";
import B6Bee from "./B6Bee";

// The bee is decoration riding on the colour scheme: rare, and never in the way.

const reducedMotion = (reduce: boolean) => {
  window.matchMedia = ((query: string) => ({
    matches: query.includes("reduced-motion") ? reduce : false,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  })) as unknown as typeof window.matchMedia;
};

const flip = (n: number) => {
  for (let i = 0; i < n; i += 1) act(() => void window.dispatchEvent(new CustomEvent(THEME_EVENT)));
};

const flying = () => document.querySelectorAll(".b6-flight").length;

describe("the B6 bee and the colour scheme", () => {
  beforeEach(() => {
    localStorage.setItem("adobee-locale", "en");
    reducedMotion(false);
  });
  afterEach(() => vi.restoreAllMocks());

  it("stays asleep for the first flips, so the surprise is not an animation you sit through", () => {
    render(
      <I18nProvider>
        <B6Bee />
      </I18nProvider>,
    );
    flip(1);
    expect(flying()).toBe(0);
    flip(1);
    expect(flying()).toBe(0);
  });

  it("wakes on the third flip", () => {
    render(
      <I18nProvider>
        <B6Bee />
      </I18nProvider>,
    );
    flip(3);
    expect(flying()).toBe(1);
  });

  it("never moves for a reader who asked for no motion, however many times the scheme flips", () => {
    reducedMotion(true);
    render(
      <I18nProvider>
        <B6Bee />
      </I18nProvider>,
    );
    flip(9);
    expect(flying()).toBe(0);
  });
});
