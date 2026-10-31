import { act, render, screen } from "@testing-library/react";
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
      output: { id: "hotel-rheinblick", name: "Hotel Rheinblick", trust: { signature_valid: true } },
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

// The chat plays its messages at a human pace; Skip jumps to the end, as a presenter would.
async function skipAhead(user: ReturnType<typeof userEvent.setup>) {
  await act(async () => {});
  const skip = screen.queryByRole("button", { name: en["chat.skip"] });
  if (skip) await user.click(skip);
}

const CAFE = {
  id: "cafe-bienli",
  slug: "cafe-bienli",
  kind: "cafe",
  name: "Café Bienli",
  tagline: "Coffee by the river",
  version: 3,
  features: ["dog-friendly"],
  units: [],
  published_at: "2026-10-30T10:00:00Z",
  trust: { signature_valid: true, attestations: [], verified_reviews: { count: 0, average: null, recent: [] } },
} as never;

describe("traveller agent", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.setItem("adobee-locale", "en");
    // Behind the door, the card tab reads a card as soon as the page opens.
    vi.spyOn(api, "cards").mockResolvedValue([]);
    vi.spyOn(api, "card").mockRejectedValue(new Error("offline"));
  });

  it("asks the agent and stops at the gate without booking", async () => {
    const agent = vi.spyOn(api, "agent").mockResolvedValue(RESULT);
    const approve = vi.spyOn(api, "approve");
    const user = setup();

    await user.click(screen.getByRole("button", { name: en["agent.send"] }));
    await skipAhead(user);

    expect(agent).toHaveBeenCalledWith([{ role: "user", content: en["agent.example.1"] }], {});
    expect(await screen.findByRole("heading", { name: gateQuestion })).toBeInTheDocument();
    // The sceptic says it in the chat, and the gate repeats it next to the question.
    expect(screen.getAllByText("Quiet, dog-friendly, under budget.")).toHaveLength(2);
    expect(approve).not.toHaveBeenCalled();
  });

  it("books exactly the held booking when the traveller approves", async () => {
    vi.spyOn(api, "agent").mockResolvedValue(RESULT);
    const approve = vi.spyOn(api, "approve").mockResolvedValue(APPROVAL);
    const user = setup();

    await user.click(screen.getByRole("button", { name: en["agent.send"] }));
    await skipAhead(user);
    await user.click(await screen.findByRole("button", { name: en["agent.approve"] }));

    expect(approve).toHaveBeenCalledWith(HELD);
    await skipAhead(user);
    expect(await screen.findByText(en["agent.receipt.eyebrow"])).toBeInTheDocument();
    expect(screen.getByText("bk_123")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: en["agent.approve"] })).not.toBeInTheDocument();
  });

  it("books nothing when the traveller declines", async () => {
    vi.spyOn(api, "agent").mockResolvedValue(RESULT);
    const approve = vi.spyOn(api, "approve");
    const user = setup();

    await user.click(screen.getByRole("button", { name: en["agent.send"] }));
    await skipAhead(user);
    await user.click(await screen.findByRole("button", { name: en["agent.decline"] }));
    await skipAhead(user);

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
    await skipAhead(user);

    await user.click(await screen.findByRole("button", { name: en["agent.unguarded.rerun"] }));
    await skipAhead(user);
    expect(agent).toHaveBeenLastCalledWith([{ role: "user", content: en["agent.example.1"] }], {
      scenario: "injection",
      rules: "on",
    });
    expect(await screen.findByRole("heading", { name: gateQuestion })).toBeInTheDocument();
  });

  it("sends an example with one tap", async () => {
    const agent = vi.spyOn(api, "agent").mockResolvedValue(RESULT);
    const user = setup();

    await user.click(screen.getByRole("button", { name: en["agent.example.2"] }));

    expect(agent).toHaveBeenCalledWith([{ role: "user", content: en["agent.example.2"] }], {});
  });

  it("holds the approval question until the conversation has played", async () => {
    vi.spyOn(api, "agent").mockResolvedValue(RESULT);
    const user = setup();

    await user.click(screen.getByRole("button", { name: en["agent.send"] }));
    await act(async () => {});

    expect(screen.queryByRole("button", { name: en["agent.approve"] })).not.toBeInTheDocument();
    await skipAhead(user);
    expect(await screen.findByRole("button", { name: en["agent.approve"] })).toBeInTheDocument();
  });

  it("names everyone in the conversation", async () => {
    vi.spyOn(api, "agent").mockResolvedValue(RESULT);
    const user = setup();

    await user.click(screen.getByRole("button", { name: en["agent.send"] }));
    await skipAhead(user);

    const roster = screen.getByRole("banner");
    for (const name of [
      "Tobi",
      en["chat.name.agent"],
      en["chat.name.hive"],
      "Hotel Rheinblick",
      en["chat.name.sceptic"],
    ])
      expect(roster).toHaveTextContent(name);
    expect(roster).not.toHaveTextContent(en["chat.name.mirror"]);
  });

  it("offers next steps after the booking, none of which books again", async () => {
    vi.spyOn(api, "agent").mockResolvedValue(RESULT);
    const approve = vi.spyOn(api, "approve").mockResolvedValue(APPROVAL);
    vi.spyOn(api, "card").mockResolvedValue({
      address: "Unterer Rheinweg 41, 4058 Basel",
      distances_m: { "basel sbb": 1900 },
    } as never);
    vi.spyOn(api, "cards").mockResolvedValue([
      { id: "cafe-bienli", slug: "cafe-bienli", name: "Café Bienli", features: ["dog-friendly"] } as never,
    ]);
    const user = setup();

    await user.click(screen.getByRole("button", { name: en["agent.send"] }));
    await skipAhead(user);
    await user.click(await screen.findByRole("button", { name: en["agent.approve"] }));
    await skipAhead(user);

    expect(await screen.findByRole("button", { name: en["next.calendar.cta"] })).toBeInTheDocument();
    expect(screen.getByText("Café Bienli")).toBeInTheDocument();
    expect(screen.getByText(en["next.coffee.because"].replace("{feature}", "dog-friendly"))).toBeInTheDocument();
    expect(screen.getByRole("link", { name: en["next.route.cta"] })).toHaveAttribute(
      "href",
      expect.stringContaining("openstreetmap.org"),
    );
    expect(approve).toHaveBeenCalledTimes(1);
  });

  it("opens the nearby place's signed card on the same page", async () => {
    vi.spyOn(api, "agent").mockResolvedValue(RESULT);
    vi.spyOn(api, "approve").mockResolvedValue(APPROVAL);
    vi.spyOn(api, "card").mockImplementation(async (id) => (id === "cafe-bienli" ? CAFE : ({} as never)));
    vi.spyOn(api, "cards").mockResolvedValue([CAFE]);
    const user = setup();

    await user.click(screen.getByRole("button", { name: en["agent.send"] }));
    await skipAhead(user);
    await user.click(await screen.findByRole("button", { name: en["agent.approve"] }));
    await skipAhead(user);
    await user.click(await screen.findByRole("button", { name: en["next.coffee.cta"] }));

    expect(screen.getByRole("tab", { name: en["door.tab.card"] })).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByRole("heading", { name: "Café Bienli" })).toBeInTheDocument();
  });

  it("shows the city's missed demand behind the same door", async () => {
    vi.spyOn(api, "demand").mockResolvedValue({
      days: 7,
      searches: 40,
      unserved_searches: 12,
      features: [{ feature: "pool", asked: 9, unserved: 9 }],
    } as never);
    const user = setup();

    await user.click(screen.getByRole("tab", { name: en["door.tab.city"] }));

    expect(await screen.findByText("pool")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: en["agent.approve"] })).not.toBeInTheDocument();
  });
});
