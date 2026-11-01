import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "../i18n";
import en from "../i18n/en";
import { resolvedTheme, storedTheme } from "../lib/theme";
import ThemeToggle from "./ThemeToggle";

// Three states, because "dark mode on/off" cannot say the true default. `system` is its own state and is what
// an address with nothing stored uses.

/** A matchMedia whose answer can change under the page, as an operating system's does at sunset. */
function osIsDark(dark: boolean) {
  const listeners: (() => void)[] = [];
  window.matchMedia = ((query: string) => ({
    matches: query.includes("dark") ? dark : false,
    media: query,
    addEventListener: (_: string, fn: () => void) => listeners.push(fn),
    removeEventListener: () => {},
  })) as unknown as typeof window.matchMedia;
  return {
    change(next: boolean) {
      dark = next;
      listeners.forEach((fn) => fn());
    },
  };
}

const draw = () =>
  render(
    <I18nProvider>
      <ThemeToggle />
    </I18nProvider>,
  );

const button = (name: string) => screen.getByRole("radio", { name });
const themeAttr = () => document.documentElement.getAttribute("data-theme");

describe("choosing a colour scheme", () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem("adobee-locale", "en");
    document.documentElement.removeAttribute("data-theme");
    osIsDark(false);
  });
  afterEach(() => vi.restoreAllMocks());

  it("follows the system until somebody says otherwise", () => {
    draw();
    expect(button(en["theme.system"])).toBeChecked();
    // No attribute at all: the stylesheet's prefers-color-scheme rule is guarded with
    // :not([data-theme="light"]), so an absent attribute is what lets the operating system through.
    expect(themeAttr()).toBeNull();
    expect(localStorage.getItem("adobee-theme")).toBeNull();
  });

  it("forces light, and says so, over a dark system", async () => {
    osIsDark(true);
    draw();
    await userEvent.click(button(en["theme.light"]));

    expect(themeAttr()).toBe("light");
    expect(localStorage.getItem("adobee-theme")).toBe("light");
    expect(button(en["theme.light"])).toBeChecked();
  });

  it("forces dark over a light system", async () => {
    draw();
    await userEvent.click(button(en["theme.dark"]));

    expect(themeAttr()).toBe("dark");
    expect(localStorage.getItem("adobee-theme")).toBe("dark");
  });

  it("goes back to following the system, and forgets the choice rather than storing one", async () => {
    draw();
    await userEvent.click(button(en["theme.dark"]));
    expect(themeAttr()).toBe("dark");

    await userEvent.click(button(en["theme.system"]));

    expect(themeAttr()).toBeNull();
    // Storing "system" would pin a reader who never touched the control to whatever their laptop was doing
    // the day they first opened the page. The key goes instead.
    expect(localStorage.getItem("adobee-theme")).toBeNull();
  });

  it("opens on a choice made on an earlier visit", () => {
    localStorage.setItem("adobee-theme", "dark");
    draw();
    expect(button(en["theme.dark"])).toBeChecked();
    expect(themeAttr()).toBe("dark");
  });

  it("tracks the system changing mid-session, and stops once a choice is made", () => {
    const os = osIsDark(false);
    draw();
    expect(resolvedTheme()).toBe("light");

    // Sunset. Nothing on the page has to re-render: with no attribute the browser re-evaluates the media
    // query itself, which is the case a hand-rolled listener usually gets wrong.
    os.change(true);
    expect(themeAttr()).toBeNull();
    expect(resolvedTheme()).toBe("dark");

    // Once light is chosen it stays light, whatever the system does next.
    expect(resolvedTheme("light")).toBe("light");
  });

  it("falls back to following the system when storage is blocked", () => {
    const get = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(storedTheme()).toBe("system");
    get.mockRestore();
  });
});
