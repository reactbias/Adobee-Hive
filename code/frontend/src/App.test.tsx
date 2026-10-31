import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "./api";
import App from "./App";
import { I18nProvider } from "./i18n";
import en from "./i18n/en";

// The app is one page: the traveller's group chat, with everything else behind the same door. api.ts is mocked.
//
// A first visit now lands on the instance finder, because you pick a Hive before you use one. These tests
// describe the app *after* a hub is chosen, so they set the choice the finder would have made; the finder's own
// behaviour is at the bottom of this file and in panels/InstanceFinder.test.tsx.

describe("the app", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.setItem("adobee-locale", "en");
    sessionStorage.setItem("adobee-hub", "local");
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
    expect(screen.getByRole("heading", { name: en["chapter.business.title"].replace(/\*/g, "") })).toBeInTheDocument();
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

  it("opens the business chapter on the owner studio, with the demand map one tab away", () => {
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );
    expect(screen.getByRole("tab", { name: en["business.tab.owner"] })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: en["business.tab.demand"] })).toHaveAttribute("aria-selected", "false");
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

  it("shows visitors no presenter tools", async () => {
    window.history.replaceState(null, "", "/");
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );
    expect(screen.queryByText(en["agent.test.eyebrow"])).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: en["demand.simulate"] })).not.toBeInTheDocument();
  });

  it("gives presenters their tools with ?demo", async () => {
    window.history.replaceState(null, "", "/?demo");
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );
    expect(screen.getByText(en["agent.test.eyebrow"])).toBeInTheDocument();
    screen.getByRole("tab", { name: en["business.tab.demand"] }).click();
    expect(await screen.findByRole("button", { name: en["demand.simulate"] })).toBeInTheDocument();
    window.history.replaceState(null, "", "/");
  });

  it("offers an obvious way back to change hub", () => {
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );
    expect(screen.getByRole("button", { name: en["finder.change"] })).toBeInTheDocument();
  });
});

// Pick a door before you walk through it. The finder must never stand between the pitch driver and a booking run,
// so a remembered choice and `?hub=` both skip it.
describe("the first screen", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.setItem("adobee-locale", "en");
    sessionStorage.clear();
    window.history.replaceState(null, "", "/");
    vi.spyOn(api, "health").mockResolvedValue({ llm: "mock", model: "", fast_model: "" } as never);
    vi.spyOn(api, "directory").mockResolvedValue({ hubs: [] });
  });

  it("is the instance finder when no hub has been chosen", async () => {
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );
    expect(await screen.findByRole("heading", { name: en["finder.title"] })).toBeInTheDocument();
    expect(screen.queryByLabelText(en["agent.intent"])).toBeNull();
  });

  it("is skipped once a hub has been chosen in this tab", () => {
    sessionStorage.setItem("adobee-hub", "local");
    vi.spyOn(api, "cards").mockResolvedValue([]);
    vi.spyOn(api, "card").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "owner").mockRejectedValue(new Error("offline"));
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );
    expect(screen.getByLabelText(en["agent.intent"])).toBeInTheDocument();
  });

  it("is skipped by ?hub= in the address, which is what the pitch runbook uses", () => {
    window.history.replaceState(null, "", "/?hub=local");
    vi.spyOn(api, "cards").mockResolvedValue([]);
    vi.spyOn(api, "card").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "owner").mockRejectedValue(new Error("offline"));
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );
    expect(screen.getByLabelText(en["agent.intent"])).toBeInTheDocument();
    window.history.replaceState(null, "", "/");
  });

  it("opens the hub's own panel with ?admin, and asks for the password", () => {
    window.history.replaceState(null, "", "/?admin");
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );
    expect(screen.getByLabelText(en["admin.password"])).toBeInTheDocument();
    expect(screen.queryByLabelText(en["agent.intent"])).toBeNull();
    window.history.replaceState(null, "", "/");
  });
});
