import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, type ActivityEvent } from "../api";
import { I18nProvider } from "../i18n";
import de from "../i18n/de";
import en from "../i18n/en";
import ActivityPanel from "./ActivityPanel";

// The presenter's window into the backend: one line per agent step, newest first, polled while the tab is open.
// api.ts is mocked.

const line = (n: number, over: Partial<ActivityEvent>): ActivityEvent => ({
  n,
  run: "r1",
  at: "2026-10-31T09:00:00Z",
  agent: "traveller",
  step: "discover",
  business: null,
  outcome: "matched",
  source: null,
  count: null,
  ...over,
});

const FEED = [
  line(1, { step: "discover", business: "Hotel Rheinblick", source: "partner", count: 3 }),
  line(2, { step: "hold", business: "Hotel Rheinblick", outcome: "held", source: "partner" }),
  line(3, { run: "r2", agent: "concierge", step: "hold", business: "BeKenya", outcome: "handoff_only", source: "web" }),
  line(4, { run: "r3", agent: "scout", step: "verify", business: "Taxi Muster", outcome: "added", source: "web" }),
];

function renderPanel(locale = "en") {
  window.localStorage.setItem("adobee-locale", locale);
  return render(
    <I18nProvider>
      <ActivityPanel />
    </I18nProvider>,
  );
}

describe("the live activity feed", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    vi.spyOn(api, "activity").mockResolvedValue({ events: FEED, last: 4 });
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    window.localStorage.clear();
  });

  it("shows each step with its agent, business and outcome, newest first", async () => {
    renderPanel();
    const rows = await screen.findAllByRole("listitem");
    expect(rows[0]).toHaveTextContent(en["activity.agent.scout"]);
    expect(rows[0]).toHaveTextContent("Taxi Muster");
    expect(rows[0]).toHaveTextContent(en["activity.outcome.added"]);
    expect(rows.at(-1)).toHaveTextContent(en["activity.step.discover"]);
    expect(rows.at(-1)).toHaveTextContent(en["activity.source.partner"]);
  });

  it("says plainly when a web result can only be handed off", async () => {
    renderPanel();
    expect(await screen.findByText(en["activity.outcome.handoff_only"])).toBeInTheDocument();
    expect(screen.getAllByText(en["activity.source.web"]).length).toBeGreaterThan(0);
  });

  it("asks only for what is new on the next poll", async () => {
    renderPanel();
    await screen.findAllByRole("listitem");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    expect(api.activity).toHaveBeenLastCalledWith(4);
  });

  it("speaks the page's language", async () => {
    renderPanel("de");
    expect(await screen.findByText(de["activity.outcome.handoff_only"])).toBeInTheDocument();
  });

  it("says so when nothing has happened yet", async () => {
    vi.spyOn(api, "activity").mockResolvedValue({ events: [], last: 0 });
    renderPanel();
    expect(await screen.findByText(en["activity.empty"])).toBeInTheDocument();
  });
});
