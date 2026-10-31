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
    vi.spyOn(api, "activity").mockResolvedValue({ events: [], last: 0 });
    vi.spyOn(api, "discover").mockRejectedValue(new Error("offline"));
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

  it("tells one journey: Search, then Opportunities", () => {
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );

    const chapters = within(screen.getByRole("navigation", { name: en["nav.chapters"] }));
    const links = chapters.getAllByRole("link");
    expect(links.map((a) => a.getAttribute("href"))).toEqual(["#travel", "#business"]);
    expect(links[0]).toHaveTextContent(en["chapter.travel"]);
    expect(links[1]).toHaveTextContent(en["chapter.business"]);
    expect(screen.getByRole("heading", { name: en["chapter.business.title"].replace(/\*/g, "") })).toBeInTheDocument();
    // Nothing is drawn until an endpoint returns it: no empty stage, no empty log.
    expect(screen.queryByRole("region", { name: en["card.stage"] })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: en["card.log"] })).not.toBeInTheDocument();
  });

  it("keeps Search as one stack and Opportunities as a brief beside one panel", () => {
    const { container } = render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );
    const search = container.querySelector("section#travel");
    expect(search?.classList.contains("stack")).toBe(true);
    expect(search?.querySelector(":scope > .frame")).toBeNull();
    const grid = container.querySelector("section#business > .chapter-grid");
    expect(grid).not.toBeNull();
    expect(grid!.querySelector(":scope > .brief")).not.toBeNull();
    expect(grid!.querySelector(":scope > .frame")).not.toBeNull();
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
});
