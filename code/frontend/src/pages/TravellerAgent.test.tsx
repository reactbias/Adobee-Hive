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
    guest_name: "Mara Keller",
  },
};

const RESULT: AgentResult = {
  reply: "Hotel Rheinblick fits. Shall I book it?",
  mode: "offline",
  pending: HELD,
  second_opinion: { verdict: "agree", note: "Quiet, dog-friendly, under budget.", by: "Rule check", ms: 1 },
  critic: {
    challenge: "Why Hotel Rheinblick? Gare Central is CHF 40 a night cheaper.",
    answer: "Hotel Rheinblick scores 82 on the Hive's open ranking, Gare Central only 61: it fits your wishes better.",
    verdict: "agree",
    note: "Fair. I agree.",
    rival: "Gare Central",
  },
  consensus: true,
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

// A stay that the cards cover is drawn first. The agent chat is the details.
async function openDetails(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: en["card.details"] }));
  // Details is the finished conversation, so the question is already there.
  await screen.findByRole("heading", { name: gateQuestion });
}

describe("traveller agent", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.setItem("adobee-locale", "en");
    // The business chapter reads the owner's view and the demand map as soon as the page opens.
    vi.spyOn(api, "cards").mockResolvedValue([]);
    vi.spyOn(api, "discover").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "card").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "owner").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "demand").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "activity").mockResolvedValue({ events: [], last: 0 });
  });

  it("keeps the search on the page, with the corpus chips and the buttons under them", async () => {
    vi.spyOn(api, "agent").mockResolvedValue(RESULT);
    const user = setup();

    // The question is the screen's one h1, and the bar sits right under it.
    const title = screen.getByRole("heading", { level: 1 });
    expect(title).toHaveTextContent(en["find.title"]);
    const box = screen.getByRole("textbox", { name: en["agent.intent"] });
    expect(title.compareDocumentPosition(box) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    const chip = screen.getByRole("button", { name: en["try.coffee"] });
    const send = screen.getByRole("button", { name: en["agent.send"] });
    expect(box.compareDocumentPosition(chip) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(chip.compareDocumentPosition(send) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // Federation is the product, so how far to search is on the bar for every visitor.
    expect(screen.getByRole("radio", { name: en["reach.local"] })).toBeInTheDocument();

    await user.click(send);
    expect(await screen.findByRole("textbox", { name: en["agent.followUp"] })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: en["try.tavern"] })).toBeInTheDocument();
  });

  it("shows every visitor how far to search, and starts at the neighbours", async () => {
    // Federation is the product. A control only a presenter can see, defaulting to this Hive alone,
    // made the whole of it invisible from the browser.
    const discover = vi.spyOn(api, "discover").mockResolvedValue({ matches: [], excluded: [], ranking_policy: "" });
    vi.spyOn(api, "agent").mockResolvedValue(RESULT);
    const user = setup();

    expect(screen.getByRole("radio", { name: en["reach.near"] })).toBeChecked();
    await user.click(screen.getByRole("button", { name: en["agent.send"] }));
    expect(discover).toHaveBeenLastCalledWith(expect.objectContaining({ radius: 1 }));

    await user.click(screen.getByRole("button", { name: en["agent.newTrip"] }));
    // New trip starts over at the same reach a first search does, never back inside one Hive.
    expect(screen.getByRole("radio", { name: en["reach.near"] })).toBeChecked();
  });

  it("re-asks the request on screen when the reach changes, rather than the next one typed", async () => {
    // A neighbour has the electrician; this Hive has hotels, which earn a point or two for their
    // attestations whatever was asked. Those are not a result.
    const neighbour = {
      id: "elektro-mattenhof",
      name: "Elektro Mattenhof",
      description: "Fuse boxes and house wiring.",
      score: 16,
      score_breakdown: { text_relevance: 0, offers_needs: 0, semantic: 16, attestations: 0 },
      provenance: { path: ["bern", "basel"] },
    };
    const hotel = {
      id: "hotel-rheinblick",
      name: "Hotel Rheinblick",
      description: "By the Rhine.",
      score: 2,
      score_breakdown: { text_relevance: 0, offers_needs: 0, semantic: 0, attestations: 2 },
    };
    const discover = vi.spyOn(api, "discover").mockImplementation(
      async (query = {}) =>
        ({
          matches: query.radius ? [neighbour, hotel] : [hotel],
          excluded: [],
          ranking_policy: "open",
        }) as never,
    );
    vi.spyOn(api, "card").mockRejectedValue(new Error("offline"));
    vi.spyOn(api, "agent").mockResolvedValue(RESULT);
    const user = setup();

    const box = screen.getByRole("textbox", { name: en["agent.intent"] });
    await user.clear(box);
    await user.type(box, "an electrician for a broken fuse box{Enter}");
    expect(await screen.findByRole("heading", { name: "Elektro Mattenhof" })).toBeInTheDocument();
    expect(discover).toHaveBeenLastCalledWith(expect.objectContaining({ radius: 1 }));
    // The hub's own hotels scored only for their reputation, so they are not drawn as answers.
    expect(screen.queryByRole("heading", { name: "Hotel Rheinblick" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: en["reach.local"] }));

    // The same question, asked again at the new reach — not held for whatever is typed next.
    expect(discover).toHaveBeenLastCalledWith({ query: "an electrician for a broken fuse box", radius: 0 });
    expect(await screen.findByText(en["reach.empty"])).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Elektro Mattenhof" })).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Hotel Rheinblick" })).not.toBeInTheDocument();
  });

  it("closes and reopens details while the agent is still working, asking it only once", async () => {
    // The old guard refused to open while busy, without saying so: one click closed the panel and
    // the next did nothing at all, which is what made the button look broken.
    let settle: (result: AgentResult) => void = () => {};
    vi.spyOn(api, "agent").mockReturnValue(new Promise<AgentResult>((resolve) => (settle = resolve)));
    const user = setup();

    await user.click(screen.getByRole("button", { name: en["agent.send"] }));
    const details = await screen.findByRole("button", { name: en["card.details"] });

    await user.click(details);
    expect(details).toHaveAttribute("aria-pressed", "true");
    await user.click(details);
    expect(details).toHaveAttribute("aria-pressed", "false");
    await user.click(details);
    expect(details).toHaveAttribute("aria-pressed", "true");
    expect(api.agent).toHaveBeenCalledTimes(1);

    await act(async () => settle(RESULT));
    expect(await screen.findByRole("heading", { name: gateQuestion })).toBeInTheDocument();
  });

  it("asks the agent and stops at the gate without booking", async () => {
    const agent = vi.spyOn(api, "agent").mockResolvedValue(RESULT);
    const approve = vi.spyOn(api, "approve");
    const user = setup();

    await user.click(screen.getByRole("button", { name: en["agent.send"] }));
    await openDetails(user);

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
    await openDetails(user);
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
    await openDetails(user);
    await user.click(await screen.findByRole("button", { name: en["agent.decline"] }));
    await skipAhead(user);

    expect(screen.getByText(en["agent.declined"])).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: gateQuestion })).not.toBeInTheDocument();
    expect(approve).not.toHaveBeenCalled();
  });

  it("keeps the card and shows the error when details cannot be opened", async () => {
    vi.spyOn(api, "agent").mockRejectedValue(new Error("Too many requests. Try again later."));
    const user = setup();

    await user.click(screen.getByRole("button", { name: en["agent.send"] }));
    await user.click(await screen.findByRole("button", { name: en["card.details"] }));

    expect(await screen.findByText("Too many requests. Try again later.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Hotel Krafft Basel" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: en["agent.followUp"] })).toHaveValue("");
  });

  it("sends the stress test with rules off, then reruns with rules on (presenters, ?demo)", async () => {
    window.history.replaceState(null, "", "/?demo");
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

    await user.click(screen.getByRole("button", { name: en["try.tavern"] }));

    expect(agent).toHaveBeenCalledWith([{ role: "user", content: en["try.tavern"] }], {});
  });

  it("reads the hub log all along and shows it beside the chat when details opens", async () => {
    const activity = vi.spyOn(api, "activity").mockResolvedValue({
      events: [
        {
          n: 1,
          run: "r1",
          at: "2026-10-31T09:00:00Z",
          agent: "traveller",
          step: "discover",
          business: "Hotel Rheinblick",
          outcome: "matched",
          source: "partner",
          count: 3,
        },
      ],
      last: 1,
    });
    vi.spyOn(api, "agent").mockResolvedValue(RESULT);
    const user = setup();

    await vi.waitFor(() => expect(activity).toHaveBeenCalled());
    expect(screen.queryByRole("region", { name: en["card.log"] })).not.toBeInTheDocument();
    const before = activity.mock.calls.length;

    await user.click(screen.getByRole("button", { name: en["agent.send"] }));
    await user.click(await screen.findByRole("button", { name: en["card.details"] }));

    expect(activity.mock.calls.length).toBeGreaterThan(before);
    // Already read before the click: the log is there at once, next to the cards.
    const log = screen.getByRole("region", { name: en["card.log"] });
    expect(log).toHaveTextContent(en["activity.step.discover"]);
    expect(log).toHaveTextContent(en["activity.outcome.matched"].replace("{n}", "3"));
    expect(screen.getByRole("heading", { name: "Hotel Krafft Basel" })).toBeInTheDocument();
  });

  it("offers New trip only once there is a trip", async () => {
    const user = setup();
    expect(screen.queryByRole("button", { name: en["agent.newTrip"] })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: en["agent.send"] }));
    expect(await screen.findByRole("button", { name: en["agent.newTrip"] })).toBeInTheDocument();
  });

  it("stays on the card when details cannot reach the backend", async () => {
    vi.spyOn(api, "agent").mockRejectedValue(new Error("500 Internal Server Error"));
    const user = setup();

    await user.click(screen.getByRole("button", { name: en["agent.send"] }));
    await user.click(await screen.findByRole("button", { name: en["card.details"] }));

    expect(await screen.findByText(en["error.offline"])).toBeInTheDocument();
    expect(screen.queryByText("500 Internal Server Error")).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Hotel Krafft Basel" })).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: en["agent.followUp"] })).toHaveValue("");
  });

  it("opens the whole chat from details, question included", async () => {
    vi.spyOn(api, "agent").mockResolvedValue(RESULT);
    const user = setup();

    await user.click(screen.getByRole("button", { name: en["agent.send"] }));
    await user.click(await screen.findByRole("button", { name: en["card.details"] }));

    expect(await screen.findByRole("button", { name: en["agent.approve"] })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: en["chat.skip"] })).not.toBeInTheDocument();
    expect(screen.getByText(RESULT.critic!.challenge)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Hotel Krafft Basel" })).toBeInTheDocument();
  });

  it("names everyone in the conversation", async () => {
    vi.spyOn(api, "agent").mockResolvedValue(RESULT);
    const user = setup();

    await user.click(screen.getByRole("button", { name: en["agent.send"] }));
    await openDetails(user);

    const roster = screen.getByRole("banner");
    for (const name of [
      "Mara",
      en["chat.name.agent"],
      en["chat.name.hive"],
      "Hotel Rheinblick",
      en["chat.name.sceptic"],
      en["chat.name.critic"],
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
      {
        id: "cafe-bienli",
        slug: "cafe-bienli",
        name: "Café Bienli",
        features: ["dog-friendly"],
        trust: { signature_valid: true },
      } as never,
    ]);
    const user = setup();

    await user.click(screen.getByRole("button", { name: en["agent.send"] }));
    await openDetails(user);
    await user.click(await screen.findByRole("button", { name: en["agent.approve"] }));
    await skipAhead(user);

    expect(await screen.findByRole("button", { name: en["next.calendar.cta"] })).toBeInTheDocument();
    expect(screen.getByText("Café Bienli", { selector: "b" })).toBeInTheDocument();
    expect(screen.getByText(en["next.coffee.because"].replace("{feature}", "dog-friendly"))).toBeInTheDocument();
    expect(screen.getByRole("link", { name: en["next.route.cta"] })).toHaveAttribute(
      "href",
      expect.stringContaining("openstreetmap.org"),
    );
    expect(approve).toHaveBeenCalledTimes(1);
  });

  it("turns the page to the hotel's side after the booking, naming the hotel just booked", async () => {
    vi.spyOn(api, "agent").mockResolvedValue(RESULT);
    vi.spyOn(api, "approve").mockResolvedValue(APPROVAL);
    vi.spyOn(api, "card").mockResolvedValue({ id: "hotel-rheinblick", slug: "rheinblick" } as never);
    const open = vi.fn();
    render(
      <I18nProvider>
        <TravellerAgent onOpenBusiness={open} />
      </I18nProvider>,
    );
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: en["agent.send"] }));
    await openDetails(user);
    await user.click(await screen.findByRole("button", { name: en["agent.approve"] }));
    await skipAhead(user);

    await user.click(await screen.findByRole("button", { name: en["next.business.cta"] }));
    expect(open).toHaveBeenCalledWith("hotel-rheinblick");
  });

  it("lets three agents argue before it asks: the critic challenges, your agent answers, all agree", async () => {
    vi.spyOn(api, "agent").mockResolvedValue(RESULT);
    const user = setup();

    await user.click(screen.getByRole("button", { name: en["agent.send"] }));
    await openDetails(user);

    expect(screen.getByText(RESULT.critic!.challenge)).toBeInTheDocument();
    expect(screen.getByText(RESULT.critic!.answer)).toBeInTheDocument();
    expect(screen.getAllByText(en["chat.consensus.agree"]).length).toBeGreaterThan(0);
    expect(await screen.findByRole("button", { name: en["agent.approve"] })).toBeInTheDocument();
  });

  it("says plainly when the three agents do not agree, and still leaves the yes to the traveller", async () => {
    vi.spyOn(api, "agent").mockResolvedValue({
      ...RESULT,
      critic: {
        ...RESULT.critic!,
        answer: "",
        verdict: "concern",
        note: "Not convinced: Gare Central ranks at least as high.",
      },
      consensus: false,
    });
    const user = setup();

    await user.click(screen.getByRole("button", { name: en["agent.send"] }));
    await openDetails(user);

    expect(screen.getAllByText(en["chat.consensus.split"]).length).toBeGreaterThan(0);
    expect(screen.getAllByText("Not convinced: Gare Central ranks at least as high.").length).toBeGreaterThan(0);
    expect(await screen.findByRole("button", { name: en["agent.approve"] })).toBeInTheDocument();
  });

  it("draws the rooms the hub returned, including one that came through Zürich", async () => {
    vi.spyOn(api, "discover").mockResolvedValue({
      matches: [
        {
          id: "pension-limmat",
          slug: "limmat",
          name: "Pension Limmat",
          description: "A quiet room in Zürich.",
          rating: 4.2,
          rating_count: 4,
          kind: "hotel",
          from_price_chf: 110,
          distance_m: null,
          score: 70,
          score_breakdown: {},
          why: ["reached through zurich"],
          signature_valid: true,
          hops: 1,
          provenance: { path: ["zurich", "basel"], hops: 1, origin: "zurich", origin_url: null, also_reached_by: [] },
        },
      ],
      excluded: [],
      ranking_policy: "open",
    });
    vi.spyOn(api, "card").mockResolvedValue({
      id: "pension-limmat",
      name: "Pension Limmat",
      description: "A quiet room in Zürich.",
      units: [{ id: "room", name: "River room", price_chf: 110 }],
    } as never);
    const user = setup();

    await user.click(screen.getByRole("button", { name: en["agent.send"] }));

    expect(await screen.findByRole("heading", { name: "Pension Limmat" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Pension Limmat" }));
    expect(screen.getByText("Through zurich → basel")).toBeInTheDocument();
    expect(await screen.findByRole("button", { name: /River room/ })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Hotel Krafft Basel" })).not.toBeInTheDocument();
  });

  it("books from the cards exactly as from Details: the agent's hold, one yes, the same receipt", async () => {
    vi.spyOn(api, "discover").mockResolvedValue({
      matches: [{ id: "hotel-rheinblick", name: "Hotel Rheinblick", description: "By the Rhine.", score: 80 }],
      excluded: [],
      ranking_policy: "open",
    } as never);
    vi.spyOn(api, "card").mockResolvedValue({
      id: "hotel-rheinblick",
      name: "Hotel Rheinblick",
      description: "By the Rhine.",
      units: [{ id: "river", name: "River-view double", price_chf: 180 }],
    } as never);
    const agent = vi.spyOn(api, "agent").mockResolvedValue(RESULT);
    const approve = vi.spyOn(api, "approve").mockResolvedValue(APPROVAL);
    const user = setup();

    await user.click(screen.getByRole("button", { name: en["agent.send"] }));
    await user.click(await screen.findByRole("button", { name: "Hotel Rheinblick" }));
    await user.click(await screen.findByRole("button", { name: /River-view double/ }));
    expect(agent).not.toHaveBeenCalled();
    await user.click(await screen.findByRole("button", { name: en["card.yes"] }));

    expect(agent).toHaveBeenCalledTimes(1);
    expect(await screen.findByRole("heading", { name: gateQuestion })).toBeInTheDocument();
    expect(screen.getByText(en["card.status.held"])).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: en["card.log"] })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: en["agent.approve"] }));

    expect(approve).toHaveBeenCalledWith(HELD);
    expect(await screen.findByText("bk_123")).toBeInTheDocument();
    expect(screen.getByText(en["card.status.booked"])).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: en["agent.approve"] })).not.toBeInTheDocument();

    // Details opens on the same run: nothing is asked or booked twice.
    await user.click(screen.getByRole("button", { name: en["card.details"] }));
    expect(agent).toHaveBeenCalledTimes(1);
    expect(approve).toHaveBeenCalledTimes(1);
  });

  it("sends on Enter, and Shift+Enter starts a new line instead", async () => {
    const agent = vi.spyOn(api, "agent").mockResolvedValue(RESULT);
    const user = setup();
    const box = screen.getByRole("textbox", { name: en["agent.intent"] });

    await user.click(box);
    await user.keyboard("{Shift>}{Enter}{/Shift}");
    expect(agent).not.toHaveBeenCalled();
    expect(box).toHaveValue(en["agent.example.1"] + "\n");

    await user.keyboard("{Enter}");
    expect(agent).not.toHaveBeenCalled();
    expect(await screen.findByRole("heading", { name: "Hotel Krafft Basel" })).toBeInTheDocument();
    expect(screen.getByText("4.3 / 5")).toBeInTheDocument();
  });

  it("draws an unrated person as not rated yet, never as zero", async () => {
    vi.spyOn(api, "agent");
    const user = setup();
    const box = screen.getByRole("textbox", { name: en["agent.intent"] });

    await user.clear(box);
    await user.type(box, "A designer for a dataviz sprint.{Enter}");

    expect(await screen.findByRole("heading", { name: "Lena Hofmann" })).toBeInTheDocument();
    expect(screen.getByText(en["card.rating.none"])).toBeInTheDocument();
    expect(screen.queryByText("0.0 / 5")).not.toBeInTheDocument();
    expect(screen.queryByRole("radiogroup", { name: en["agent.review.rating"] })).not.toBeInTheDocument();
  });

  it("says the agent is on it while the request is out", async () => {
    vi.spyOn(api, "agent").mockReturnValue(new Promise(() => {}));
    const user = setup();
    const box = screen.getByRole("textbox", { name: en["agent.intent"] });
    await user.clear(box);
    await user.type(box, "A quiet night in Geneva{Enter}");
    expect(screen.getByRole("button", { name: en["agent.sending"] })).toBeDisabled();
  });

  it("asks from where to where for a bare taxi, then sends the whole request", async () => {
    const asked = {
      question: "book me a taxi",
      preference: { mood: null, effects: [], source: "chosen by you" },
      replies: [],
      excluded: [],
      budget_chf: null,
      rate: null,
      pending: null,
      rules: [],
      answer: null,
      mode: "offline",
      unserved: false,
      clarify: ["route", "time"],
    };
    const ask = vi
      .spyOn(api, "ask")
      .mockResolvedValueOnce(asked)
      .mockResolvedValueOnce({ ...asked, question: "x", clarify: [], unserved: true });
    const scout = vi
      .spyOn(api, "scout")
      .mockResolvedValue({ status: "none", added: [], rejected: [], result: null } as never);
    const user = setup();
    const box = screen.getByRole("textbox", { name: en["agent.intent"] });

    await user.clear(box);
    await user.type(box, "book me a taxi{Enter}");
    await skipAhead(user);
    expect(await screen.findByText(en["clarify.route_time"])).toBeInTheDocument();
    expect(scout).not.toHaveBeenCalled(); // nothing to look for yet

    await user.type(box, "from Basel SBB to Aesch at 17:00{Enter}");
    expect(ask).toHaveBeenLastCalledWith("book me a taxi from Basel SBB to Aesch at 17:00", null);
  });

  it("says hand-off cards cannot be booked, and holds the one the traveller names", async () => {
    const reply = (card_id: string, name: string) => ({
      card_id,
      slug: card_id,
      name,
      kind: "software",
      tagline: null,
      claimed: false,
      source: null,
      signature_valid: true,
      items: [{ id: "careers", type: "offer", title: `Jobs and careers at ${name}`, why: [], action: "See open jobs" }],
    });
    const base = {
      question: "Which companies offer jobs?",
      preference: { mood: null, effects: [], source: "chosen by you" },
      excluded: [],
      budget_chf: null,
      rate: null,
      rules: [],
      answer: null,
      mode: "offline",
      unserved: false,
      clarify: [],
    };
    const ask = vi
      .spyOn(api, "ask")
      .mockResolvedValueOnce({
        ...base,
        replies: [reply("x-adobe", "Adobe"), reply("x-pax", "Pax")],
        pending: null,
      } as never)
      .mockResolvedValueOnce({ ...base, replies: [reply("x-pax", "Pax")], pending: null } as never);
    const user = setup();
    const box = screen.getByRole("textbox", { name: en["agent.intent"] });

    await user.clear(box);
    await user.type(box, "Which companies offer jobs?{Enter}");
    await skipAhead(user);
    expect(await screen.findByText(en["chat.ask.handoff_only"])).toBeInTheDocument();
    expect(screen.getAllByText(en["trust.unclaimed"]).length).toBeGreaterThan(0);

    await user.type(box, "Pax please{Enter}");
    expect(ask).toHaveBeenLastCalledWith("Which companies offer jobs? Pax please", null, true);
  });
});
