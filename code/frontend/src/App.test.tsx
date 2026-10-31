import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";
import App from "./App";
import { I18nProvider } from "./i18n";
import en from "./i18n/en";

// The app is one page: the traveller's group chat, with everything else behind the same door. api.ts is mocked.

describe("the app", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.setItem("adobee-locale", "en");
    vi.spyOn(api, "health").mockResolvedValue({ llm: "mock", model: "", fast_model: "" } as never);
    vi.spyOn(api, "cards").mockResolvedValue([]);
    vi.spyOn(api, "card").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "owner").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "demand").mockRejectedValue(new Error("offline"));
  });

  it("opens on the traveller agent and links to no other page", async () => {
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );

    expect(screen.getByLabelText(en["agent.intent"])).toBeInTheDocument();
    expect(await screen.findByText(en["nav.offline"])).toBeInTheDocument();
    const hrefs = screen.queryAllByRole("link").map((a) => a.getAttribute("href") ?? "");
    expect(hrefs.filter((h) => !h.startsWith("#") && !/^https?:/.test(h))).toEqual([]);
  });

  it("tells one story in two chapters: your agent, then the business's side", () => {
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );

    const chapters = within(screen.getByRole("navigation", { name: en["nav.chapters"] }));
    expect(chapters.getAllByRole("link").map((a) => a.getAttribute("href"))).toEqual(["#travel", "#business"]);
    expect(screen.getByRole("heading", { name: en["owner.title"].replace(/\*/g, "") })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: en["demand.title"].replace(/\*/g, "") })).toBeInTheDocument();
  });

  it("gives every chapter the same layout: a brief beside one fixed-height panel", () => {
    const { container } = render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );
    for (const id of ["travel", "business"]) {
      const grid = container.querySelector(`section#${id} > .chapter-grid`);
      expect(grid, id).not.toBeNull();
      expect(grid!.querySelector(":scope > .brief"), id).not.toBeNull();
      expect(grid!.querySelector(":scope > .frame"), id).not.toBeNull();
    }
  });

  it("lets the business chapter jump between the demand map and the owner studio", () => {
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );
    expect(screen.getByRole("button", { name: en["business.jump.demand"] })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: en["business.jump.owner"] })).toBeInTheDocument();
  });

  it("scrolls back to the top when the logo is clicked", async () => {
    const scrollTo = vi.fn();
    window.scrollTo = scrollTo as unknown as typeof window.scrollTo;
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );
    screen.getByRole("link", { name: "Adobee Hive" }).click();
    expect(scrollTo).toHaveBeenCalledWith(expect.objectContaining({ top: 0 }));
  });
});
