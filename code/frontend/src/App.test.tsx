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

  it("tells one story in three chapters: the traveller, any business, then the business's side", () => {
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );

    const chapters = within(screen.getByRole("navigation", { name: en["nav.chapters"] }));
    expect(chapters.getAllByRole("link").map((a) => a.getAttribute("href"))).toEqual(["#travel", "#ask", "#business"]);
    expect(screen.getByRole("heading", { name: en["owner.title"].replace(/\*/g, "") })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: en["demand.title"].replace(/\*/g, "") })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: en["ask.label"] })).toBeInTheDocument();
  });
});
