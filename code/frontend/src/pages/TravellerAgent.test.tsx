import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, type AgentResult, type Approval } from "../api";
import { I18nProvider } from "../i18n";
import en from "../i18n/en";
import TravellerAgent from "./TravellerAgent";

// The /agent flow as a traveller sees it: ask, read the gate, approve or decline. api.ts is mocked.

const HELD = {
  id: "hold-1",
  tool: "hive_book" as const,
  input: {
    card_id: "hotel-rheinblick",
    unit_id: "river",
    check_in: "2026-11-13",
    check_out: "2026-11-15",
    guest_name: "Tobi Muster",
  },
};

const RESULT: AgentResult = {
  reply: "Hotel Rheinblick fits. Shall I book it?",
  mode: "offline",
  pending: HELD,
  second_opinion: { verdict: "agree", note: "Quiet, dog-friendly, under budget.", by: "Rule check", ms: 1 },
  steps: [
    {
      tool: "hive_discover",
      input: { features: ["quiet", "dog-friendly"], near: "Basel SBB" },
      output: {
        matches: [{ id: "hotel-rheinblick", name: "Hotel Rheinblick", score: 80, why: ["has quiet, dog-friendly"] }],
        excluded: [{ id: "hotel-gare", name: "Gare Central", why_not: ["missing dog-friendly"] }],
      },
    },
    {
      tool: "hive_get_card",
      input: { card_id: "hotel-rheinblick" },
      output: { id: "hotel-rheinblick", name: "Hotel Rheinblick" },
    },
    {
      tool: "hive_check_availability",
      input: { card_id: "hotel-rheinblick", check_in: "2026-11-13", check_out: "2026-11-15" },
      output: {
        available_units: [{ id: "river", name: "River-view double", price_chf: 180, total_chf: 360 }],
        policies: { cancellation: "Free until 24 h before" },
      },
    },
  ],
};

const APPROVAL: Approval = {
  reply: "Booked Hotel Rheinblick.",
  steps: [{ tool: "hive_book", input: HELD.input, output: { status: "confirmed" } }],
  booking: {
    status: "confirmed",
    booking_id: "bk_123",
    business: "Hotel Rheinblick",
    unit_name: "River-view double",
    check_in: "2026-11-13",
    check_out: "2026-11-15",
    total_chf: 360,
    receipt: "body.signature",
    payment: "Pay at the property",
  },
};

const gateQuestion = en["agent.gate.question"]
  .replace("{unit}", "River-view double")
  .replace("{name}", "Hotel Rheinblick");

function setup() {
  render(
    <I18nProvider>
      <TravellerAgent />
    </I18nProvider>,
  );
  return userEvent.setup();
}

describe("traveller agent", () => {
  beforeEach(() => {
    localStorage.setItem("adobee-locale", "en");
  });

  it("asks the agent and stops at the gate without booking", async () => {
    const agent = vi.spyOn(api, "agent").mockResolvedValue(RESULT);
    const approve = vi.spyOn(api, "approve");
    const user = setup();

    await user.click(screen.getByRole("button", { name: en["agent.send"] }));

    expect(agent).toHaveBeenCalledWith([{ role: "user", content: en["agent.example.1"] }], {});
    expect(await screen.findByRole("heading", { name: gateQuestion })).toBeInTheDocument();
    expect(screen.getByText("Quiet, dog-friendly, under budget.")).toBeInTheDocument();
    expect(approve).not.toHaveBeenCalled();
  });

  it("books exactly the held booking when the traveller approves", async () => {
    vi.spyOn(api, "agent").mockResolvedValue(RESULT);
    const approve = vi.spyOn(api, "approve").mockResolvedValue(APPROVAL);
    const user = setup();

    await user.click(screen.getByRole("button", { name: en["agent.send"] }));
    await user.click(await screen.findByRole("button", { name: en["agent.approve"] }));

    expect(approve).toHaveBeenCalledWith(HELD);
    expect(await screen.findByText(en["agent.receipt.eyebrow"])).toBeInTheDocument();
    expect(screen.getByText("bk_123")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: en["agent.approve"] })).not.toBeInTheDocument();
  });

  it("books nothing when the traveller declines", async () => {
    vi.spyOn(api, "agent").mockResolvedValue(RESULT);
    const approve = vi.spyOn(api, "approve");
    const user = setup();

    await user.click(screen.getByRole("button", { name: en["agent.send"] }));
    await user.click(await screen.findByRole("button", { name: en["agent.decline"] }));

    expect(screen.getByText(en["agent.declined"])).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: gateQuestion })).not.toBeInTheDocument();
    expect(approve).not.toHaveBeenCalled();
  });

  it("keeps the request and shows the error when the backend fails", async () => {
    vi.spyOn(api, "agent").mockRejectedValue(new Error("Too many requests. Try again later."));
    const user = setup();

    await user.click(screen.getByRole("button", { name: en["agent.send"] }));

    expect(await screen.findByText("Too many requests. Try again later.")).toBeInTheDocument();
    expect(screen.getByRole("textbox")).toHaveValue(en["agent.example.1"]);
  });

  it("sends the stress test with rules off, then reruns with rules on", async () => {
    const unguarded: AgentResult = {
      ...RESULT,
      pending: null,
      second_opinion: undefined,
      scenario: "injection",
      rules: "off",
      unguarded: {
        would_call: { tool: "hive_book", input: { ...HELD.input, card_id: "hotel-muenster", unit_id: "suite" } },
        total_chf: 780,
        broken: [{ code: "ignored_budget", text: "over budget", price_chf: 780, budget_chf: 400 }],
        sent: false,
      },
    };
    const agent = vi.spyOn(api, "agent").mockResolvedValueOnce(unguarded).mockResolvedValueOnce(RESULT);
    const user = setup();

    await user.click(screen.getByRole("checkbox", { name: en["agent.test.injection"] }));
    await user.click(screen.getByRole("checkbox", { name: en["agent.test.rulesOff"] }));
    await user.click(screen.getByRole("button", { name: en["agent.send"] }));
    expect(agent).toHaveBeenLastCalledWith(expect.anything(), { scenario: "injection", rules: "off" });

    await user.click(await screen.findByRole("button", { name: en["agent.unguarded.rerun"] }));
    expect(agent).toHaveBeenLastCalledWith([{ role: "user", content: en["agent.example.1"] }], {
      scenario: "injection",
      rules: "on",
    });
    expect(await screen.findByRole("heading", { name: gateQuestion })).toBeInTheDocument();
  });
});
