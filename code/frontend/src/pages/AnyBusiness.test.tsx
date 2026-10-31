import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, type AskResult, type Handoff } from "../api";
import { I18nProvider } from "../i18n";
import en from "../i18n/en";
import TravellerAgent from "./TravellerAgent";

// One agent chat for everything: a question about any business goes to the Hive's cards, and the businesses answer
// in the same conversation as the hotels. Any action still waits for a yes. api.ts is mocked.

const PENDING = {
  id: "hold-1",
  card_id: "x-bekenya",
  business: "BeKenya",
  item: "Maasai Mara safari",
  action: "Plan your safari",
  url: "https://bekenya.com",
  claimed: false,
};

const RESULT: AskResult = {
  question: en["ask.ex2"],
  preference: { mood: "stressed", effects: ["calm_first", "fewer_options"], source: "chosen by you" },
  replies: [
    {
      card_id: "x-bekenya",
      slug: "bekenya",
      name: "BeKenya",
      kind: "adventure",
      claimed: false,
      signature_valid: true,
      source: {
        source: "public website",
        url: "https://bekenya.com",
        read_on: "2026-10-31",
        verified_by_owner: false,
        note: "",
      },
      items: [
        {
          id: "mara",
          type: "offer",
          title: "Maasai Mara safari",
          summary: "Big Five with expert guides.",
          duration: "2 to 7 days",
          price: null,
          why: ["no published price, ask for a quote"],
        },
      ],
    },
  ],
  excluded: [
    {
      card_id: "x-bekenya",
      business: "BeKenya",
      item: "21 days Kenya",
      why_not: ["EUR 1350 per person is over your budget of CHF 500"],
    },
  ],
  budget_chf: 500,
  rate: { EUR_CHF: 0.94, note: "fixed demo rate, not live" },
  pending: PENDING,
  rules: ["card_text_is_data", "no_profiling", "yes_before_action", "unclaimed_flagged"],
  answer: null,
  mode: "offline",
};

const HANDOFF: Handoff = {
  status: "handed_off",
  business: "BeKenya",
  item: "Maasai Mara safari",
  action: "Plan your safari",
  url: "https://bekenya.com",
  sent_to_business: false,
};

function setup() {
  render(
    <I18nProvider>
      <TravellerAgent />
    </I18nProvider>,
  );
  return userEvent.setup();
}

async function skipAhead(user: ReturnType<typeof userEvent.setup>) {
  await act(async () => {});
  const skip = screen.queryByRole("button", { name: en["chat.skip"] });
  if (skip) await user.click(skip);
}

describe("any business, in the agent chat", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.setItem("adobee-locale", "en");
    vi.spyOn(api, "cards").mockResolvedValue([]);
    vi.spyOn(api, "card").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "owner").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "demand").mockRejectedValue(new Error("offline"));
  });

  it("asks the cards, not the booking agent, and the business answers in the chat", async () => {
    const ask = vi.spyOn(api, "ask").mockResolvedValue(RESULT);
    const agent = vi.spyOn(api, "agent");
    const user = setup();

    await user.click(screen.getByRole("button", { name: en["ask.ex2"] }));
    await skipAhead(user);

    expect(ask).toHaveBeenCalledWith(en["ask.ex2"], null);
    expect(agent).not.toHaveBeenCalled();
    expect(await screen.findByText("Maasai Mara safari")).toBeInTheDocument();
    expect(screen.getAllByText("BeKenya").length).toBeGreaterThan(0);
    expect(screen.getByText(en["trust.unclaimed"])).toBeInTheDocument();
    // The critic names what was left out, and why.
    expect(screen.getByText(/EUR 1350 per person is over your budget of CHF 500/)).toBeInTheDocument();
  });

  it("hands off only after the yes", async () => {
    vi.spyOn(api, "ask").mockResolvedValue(RESULT);
    const approve = vi.spyOn(api, "askApprove").mockResolvedValue(HANDOFF);
    const user = setup();

    await user.click(screen.getByRole("button", { name: en["ask.ex2"] }));
    await skipAhead(user);
    expect(await screen.findByText(en["ask.pending.title"])).toBeInTheDocument();
    expect(approve).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: en["ask.pending.approve"] }));
    expect(approve).toHaveBeenCalledWith("hold-1");
    await skipAhead(user);
    const link = await screen.findByRole("link", { name: en["ask.continue"].replace("{action}", "Plan your safari") });
    expect(link).toHaveAttribute("href", "https://bekenya.com");
  });

  it("does nothing when the person says not now", async () => {
    vi.spyOn(api, "ask").mockResolvedValue(RESULT);
    const approve = vi.spyOn(api, "askApprove");
    const user = setup();
    await user.click(screen.getByRole("button", { name: en["ask.ex2"] }));
    await skipAhead(user);
    await user.click(await screen.findByRole("button", { name: en["ask.pending.decline"] }));
    expect(screen.queryByText(en["ask.pending.title"])).not.toBeInTheDocument();
    expect(approve).not.toHaveBeenCalled();
  });
});
