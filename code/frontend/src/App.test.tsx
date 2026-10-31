import { render, screen } from "@testing-library/react";
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
  });

  it("opens on the traveller agent and links to no other page", async () => {
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );

    expect(screen.getByLabelText(en["agent.intent"])).toBeInTheDocument();
    expect(await screen.findByText(en["nav.offline"])).toBeInTheDocument();
    const inside = screen.queryAllByRole("link").filter((a) => !/^https?:/.test(a.getAttribute("href") ?? ""));
    expect(inside.map((a) => a.getAttribute("href"))).toEqual([]);
  });

  it("keeps the card, the owner, the city and the other businesses one tab away", () => {
    render(
      <I18nProvider>
        <App />
      </I18nProvider>,
    );

    const tabs = screen.getAllByRole("tab").map((t) => t.textContent);
    expect(tabs).toEqual([en["door.tab.card"], en["door.tab.owner"], en["door.tab.city"], en["door.tab.ask"]]);
  });
});
