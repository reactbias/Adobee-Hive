import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, type AskResult, type Handoff } from "../api";
import { I18nProvider } from "../i18n";
import en from "../i18n/en";
import AskHive from "./AskHive";

// /ask as a person sees it: a mood they set, answers marked unclaimed, and a yes before any hand-off. api.ts is mocked.

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
      <MemoryRouter>
        <AskHive />
      </MemoryRouter>
    </I18nProvider>,
  );
  return userEvent.setup();
}

describe("ask the Hive", () => {
  beforeEach(() => {
    localStorage.setItem("adobee-locale", "en");
  });

  it("sends the mood the person picked, and shows what it changed and the rules", async () => {
    const ask = vi.spyOn(api, "ask").mockResolvedValue(RESULT);
    const user = setup();

    await user.click(screen.getByRole("button", { name: en["ask.mood.stressed"] }));
    await user.click(screen.getByRole("button", { name: en["ask.ex2"] }));

    expect(ask).toHaveBeenCalledWith(en["ask.ex2"], "stressed");
    expect(await screen.findByText(en["ask.effect.calm_first"])).toBeInTheDocument();
    expect(screen.getByText(en["ask.rule.yes_before_action"])).toBeInTheDocument();
    expect(screen.getByText(en["trust.unclaimed"])).toBeInTheDocument();
    expect(screen.getByText("EUR 1350 per person is over your budget of CHF 500")).toBeInTheDocument();
  });

  it("sends no mood unless the person sets one", async () => {
    const ask = vi.spyOn(api, "ask").mockResolvedValue({ ...RESULT, pending: null });
    const user = setup();

    await user.click(screen.getByRole("button", { name: en["ask.ex1"] }));

    expect(ask).toHaveBeenCalledWith(en["ask.ex1"], null);
  });

  it("hands off only after the yes, and says nothing was sent", async () => {
    vi.spyOn(api, "ask").mockResolvedValue(RESULT);
    const approve = vi.spyOn(api, "askApprove").mockResolvedValue(HANDOFF);
    const user = setup();

    await user.click(screen.getByRole("button", { name: en["ask.ex2"] }));
    await screen.findByText(en["ask.pending.title"]);
    expect(approve).not.toHaveBeenCalled();

    await user.click(screen.getByRole("button", { name: en["ask.pending.approve"] }));

    expect(approve).toHaveBeenCalledWith("hold-1");
    expect(await screen.findByText(en["ask.handoff"].replace("{business}", "BeKenya"))).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Plan your safari/ })).toHaveAttribute("href", "https://bekenya.com");
  });

  it("hands off nothing when the person declines", async () => {
    vi.spyOn(api, "ask").mockResolvedValue(RESULT);
    const approve = vi.spyOn(api, "askApprove");
    const user = setup();

    await user.click(screen.getByRole("button", { name: en["ask.ex2"] }));
    await user.click(await screen.findByRole("button", { name: en["ask.pending.decline"] }));

    expect(screen.queryByText(en["ask.pending.title"])).not.toBeInTheDocument();
    expect(approve).not.toHaveBeenCalled();
  });
});
