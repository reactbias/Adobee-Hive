import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "../i18n";
import en from "../i18n/en";
import { sceneFor, sceneFromDiscovery, type Scene } from "../lib/cardView";
import GeneratedStage, { type Deal } from "./GeneratedStage";

const beat = () =>
  act(() => {
    vi.advanceTimersByTime(520);
  });

const open = (name: string) => fireEvent.click(screen.getByRole("button", { name }));

function hubCard(id: string, name: string, tagline: string) {
  return {
    id,
    kind: "hotel",
    name,
    tagline,
    description: `${name} by the river.`,
    address: "Unterer Rheinweg 41, 4058 Basel",
    features: ["dog-friendly", "quiet"],
    distances_m: { "basel sbb": 1900 },
    version: 1,
    published_at: "2026-10-31T08:41:44+00:00",
    units: [{ id: "single", name: "Courtyard single", price_chf: 128 }],
  };
}

describe("generated card", () => {
  afterEach(() => {
    vi.useRealTimers();
    window.matchMedia = undefined as never;
  });

  it("starts every card as one row, and opens only the one the person taps", () => {
    window.matchMedia = vi.fn().mockReturnValue({ matches: true }) as never;
    const scene = sceneFromDiscovery("quiet hotel", [{ id: "a" }, { id: "b" }], {
      a: hubCard("a", "Hotel Rheinblick", "Quiet rooms over the Rhine"),
      b: hubCard("b", "Hotel Krafft", "Rooms on the Rhine since 1872"),
    });
    render(
      <I18nProvider>
        <GeneratedStage scene={scene!} onDetails={() => {}} />
      </I18nProvider>,
    );

    expect(screen.getByRole("heading", { name: "Hotel Rheinblick" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Hotel Krafft" })).toBeInTheDocument();
    expect(screen.getByText("Quiet rooms over the Rhine")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Hotel Rheinblick" })).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByText("Hotel Rheinblick by the river.")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Courtyard single/ })).not.toBeInTheDocument();

    open("Hotel Rheinblick");
    expect(screen.getByRole("button", { name: "Hotel Rheinblick" })).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("Hotel Rheinblick by the river.")).toBeInTheDocument();
    expect(screen.queryByText("Hotel Krafft by the river.")).not.toBeInTheDocument();

    open("Hotel Rheinblick");
    expect(screen.queryByText("Hotel Rheinblick by the river.")).not.toBeInTheDocument();
  });

  it("opens a card one part at a time: who it is, then the offerings, then the question once one is chosen", () => {
    vi.useFakeTimers();
    const scene = sceneFor(en["agent.example.1"]);
    expect(scene).not.toBeNull();
    render(
      <I18nProvider>
        <GeneratedStage scene={scene!} onDetails={() => {}} />
      </I18nProvider>,
    );

    expect(screen.getByRole("heading", { name: "Hotel Krafft Basel" })).toBeInTheDocument();
    expect(screen.getByText("4.3 / 5")).toBeInTheDocument();
    beat();
    beat();
    expect(screen.queryByRole("button", { name: /Room reservation/ })).not.toBeInTheDocument();

    open("Hotel Krafft Basel");
    expect(screen.queryByRole("button", { name: /Room reservation/ })).not.toBeInTheDocument();
    beat();
    expect(screen.getByRole("button", { name: /Room reservation/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Small event on the Rhine terrace/ })).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Room reservation with Hotel Krafft Basel?" }),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Room reservation/ }));
    expect(screen.queryByText("Free cancellation 48h. No prepayment.")).not.toBeInTheDocument();
    beat();
    expect(screen.getByText("in-person")).toBeInTheDocument();
    expect(screen.queryByText("Free cancellation 48h. No prepayment.")).not.toBeInTheDocument();
    beat();
    expect(screen.getByText("Free cancellation 48h. No prepayment.")).toBeInTheDocument();
    beat();
    expect(screen.getByText("Quiet side rooms, dogs welcome")).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Room reservation with Hotel Krafft Basel?" }),
    ).not.toBeInTheDocument();
    beat();
    expect(screen.getByRole("heading", { name: "Room reservation with Hotel Krafft Basel?" })).toBeInTheDocument();
  });

  it("draws an opened hub card readably: tagline, feature chips, priced rooms, the rest folded away", () => {
    window.matchMedia = vi.fn().mockReturnValue({ matches: true }) as never;
    const scene = sceneFromDiscovery(
      "quiet hotel",
      [{ id: "hotel-rheinblick", why: ["mentions quiet"], provenance: { path: ["local"] } }],
      { "hotel-rheinblick": hubCard("hotel-rheinblick", "Hotel Rheinblick", "Quiet rooms over the Rhine") },
    );
    render(
      <I18nProvider>
        <GeneratedStage scene={scene!} onDetails={() => {}} />
      </I18nProvider>,
    );

    expect(screen.getByText(en["card.count.one"])).toBeInTheDocument();
    open("Hotel Rheinblick");
    expect(screen.getByText("Quiet rooms over the Rhine")).toBeInTheDocument();
    expect(screen.getByText("dog-friendly")).toBeInTheDocument();
    expect(screen.getByText("mentions quiet")).toBeInTheDocument();
    expect(screen.getByText(/Unterer Rheinweg 41/)).toBeInTheDocument();
    // One hub is not a path worth naming.
    expect(screen.queryByText(/Through/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Courtyard single.*CHF.*128/ })).toBeInTheDocument();
    expect(screen.getByText(en["card.more"].replace("{name}", "Hotel Rheinblick"))).toBeInTheDocument();
    expect(screen.getByText("basel sbb")).toBeInTheDocument();
    expect(screen.queryByText("published_at")).not.toBeInTheDocument();
    expect(screen.queryByText("version")).not.toBeInTheDocument();
  });

  describe("the yes, from the agent's own data", () => {
    const scene = () => sceneFor(en["agent.example.1"])!;
    const KRAFFT = scene().hits[0].card.id;
    const deal = (over: Partial<Deal> = {}): Deal => ({ working: false, onAsk: () => {}, ...over });
    const draw = (d: Deal, onDetails = () => {}) => (
      <I18nProvider>
        <GeneratedStage scene={scene()} onDetails={onDetails} deal={d} />
      </I18nProvider>
    );
    const pickRoom = () => {
      open("Hotel Krafft Basel");
      fireEvent.click(screen.getByRole("button", { name: /Room reservation/ }));
    };
    afterEach(() => {
      window.matchMedia = undefined as never;
    });
    const still = () => (window.matchMedia = vi.fn().mockReturnValue({ matches: true }) as never);

    it("hands the yes to the agent, and books nothing itself", () => {
      still();
      const onAsk = vi.fn();
      render(draw(deal({ onAsk })));
      pickRoom();

      fireEvent.click(screen.getByRole("button", { name: en["card.yes"] }));
      expect(onAsk).toHaveBeenCalledTimes(1);
    });

    it("says the agent is checking while it works", () => {
      still();
      render(draw(deal({ working: true })));
      pickRoom();

      expect(screen.getByText(en["card.asking"].replace("{name}", "Hotel Krafft Basel"))).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: en["card.yes"] })).not.toBeInTheDocument();
    });

    it("shows the agent's own question under the card it holds, and marks the row", () => {
      still();
      render(draw(deal({ heldFor: KRAFFT, gate: <h3>Approve the River room?</h3> })));
      expect(screen.getByText(en["card.status.held"])).toBeInTheDocument();
      pickRoom();

      expect(screen.getByRole("heading", { name: "Approve the River room?" })).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: en["card.yes"] })).not.toBeInTheDocument();
    });

    it("names the card the agent holds when it is another, and opens Details from there", () => {
      still();
      const onDetails = vi.fn();
      render(draw(deal({ heldFor: "hotel-rheinblick", heldName: "Hotel Rheinblick" }), onDetails));
      pickRoom();

      expect(screen.getByText(en["card.held.other"].replace("{name}", "Hotel Rheinblick"))).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: en["card.yes"] })).not.toBeInTheDocument();
      fireEvent.click(screen.getAllByRole("button", { name: en["card.details"] }).at(-1)!);
      expect(onDetails).toHaveBeenCalledTimes(1);
    });

    it("shows what the agent answered when it held nothing", () => {
      still();
      render(draw(deal({ answer: "Nothing fits those dates." })));
      pickRoom();

      expect(screen.getByText("Nothing fits those dates.")).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: en["card.yes"] })).not.toBeInTheDocument();
    });

    it("shows the signed receipt under the booked card, and marks the row booked", () => {
      still();
      render(draw(deal({ bookedFor: KRAFFT, receipt: <p>Receipt bk_123</p> })));
      expect(screen.getByText(en["card.status.booked"])).toBeInTheDocument();
      pickRoom();

      expect(screen.getByText("Receipt bk_123")).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: en["card.yes"] })).not.toBeInTheDocument();
    });

    it("steps back from a no to the other offerings", () => {
      still();
      render(draw(deal()));
      pickRoom();

      fireEvent.click(screen.getByRole("button", { name: en["agent.decline"] }));
      expect(screen.getByRole("button", { name: /Room reservation/ })).toHaveAttribute("aria-pressed", "false");
      expect(screen.queryByRole("button", { name: en["card.yes"] })).not.toBeInTheDocument();
    });
  });
});

// Where an answer came from: a result from another hub says so under its name, a local one says nothing extra,
// and a hub that did not answer or a copy that was refused is shown rather than swallowed.
describe("results from other hubs", () => {
  afterEach(() => {
    window.matchMedia = undefined as never;
  });

  function stage(federation: Scene["federation"], hops = 1) {
    window.matchMedia = vi.fn().mockReturnValue({ matches: true }) as never;
    const scene = sceneFromDiscovery(
      "quiet hotel",
      [
        { id: "limmat", hops, provenance: { path: ["zurich", "basel"], origin: "zurich" } },
        { id: "rhein", hops: 0 },
      ],
      {
        limmat: hubCard("limmat", "Pension Limmat", "Quiet rooms on the Limmat"),
        rhein: hubCard("rhein", "Hotel Rheinblick", "Quiet rooms over the Rhine"),
      },
    )!;
    render(
      <I18nProvider>
        <GeneratedStage scene={{ ...scene, federation }} onDetails={() => {}} />
      </I18nProvider>,
    );
  }

  const zurich = { radius: 1, asked: [{ hub: "zurich", name: "Hive Zürich" }], dropped: [], rejected: [] };

  it("names the hub and the distance for a result that travelled, and nothing for a local one", () => {
    stage(zurich);
    const rows = screen.getAllByRole("article");
    expect(rows[0]).toHaveTextContent("from Hive Zürich, 1 hop away");
    expect(rows[1]).not.toHaveTextContent(/hop/);
    // The hub's order stands: distance is already in its score.
    expect(rows[0]).toHaveTextContent("Pension Limmat");
  });

  it("says hops past one", () => {
    stage(zurich, 2);
    expect(screen.getByText("from Hive Zürich, 2 hops away")).toBeInTheDocument();
  });

  it("counts the hubs it asked, and says so plainly when there were none", () => {
    stage(zurich);
    expect(screen.getByText("1 Hive asked")).toBeInTheDocument();
    cleanup();

    stage({ radius: 1, asked: [], dropped: [], rejected: [] }, 0);
    expect(screen.getByText(en["reach.none"])).toBeInTheDocument();
    expect(screen.queryByText(/Hives? asked/)).not.toBeInTheDocument();
  });

  it("shows a hub that did not answer, and a copy that did not match what the owner signed", () => {
    stage({
      ...zurich,
      dropped: [
        { hub: "zurich", reason: "deadline exceeded: 12 ms left for this hop" },
        { hub: "geneva", reason: "no key registry: its cards could not be verified here" },
      ],
      rejected: [{ hub: "zurich", card_id: "hotel-liar", reason: "this copy does not match what the owner signed" }],
    });
    expect(screen.getByText("Hive Zürich did not answer in time")).toBeInTheDocument();
    expect(
      screen.getByText("geneva was left out: no key registry: its cards could not be verified here"),
    ).toBeInTheDocument();
    expect(screen.getByText("A copy from Hive Zürich did not match what the owner signed")).toBeInTheDocument();
  });

  it("offers to connect to a live result the way its owner allowed, and shows contact as the owner shared it", () => {
    window.matchMedia = vi.fn().mockReturnValue({ matches: true }) as never;
    const person = {
      id: "lena-hofmann",
      kind: "person",
      name: "Lena Hofmann",
      description: "Interface design for data-heavy products.",
      contact: { email: "lena@lena.example", phone: "", mobile: "" },
      contact_sharing: { phone: "confirm", address: "never" },
    };
    const scene = sceneFromDiscovery(
      "designer",
      [
        { id: "lena-hofmann", sharing: "confirm" },
        { id: "hotel-rheinblick", sharing: "public" },
      ],
      { "lena-hofmann": person, "hotel-rheinblick": hubCard("hotel-rheinblick", "Hotel Rheinblick", "Quiet") },
    );
    render(
      <I18nProvider>
        <GeneratedStage scene={scene!} onDetails={() => {}} />
      </I18nProvider>,
    );

    open("Lena Hofmann");
    expect(screen.getByRole("button", { name: en["connect.ask"] })).toBeInTheDocument();
    expect(screen.getByText(en["connect.askNote"].replace("{name}", "Lena Hofmann"))).toBeInTheDocument();
    expect(screen.getByText("lena@lena.example")).toBeInTheDocument();
    expect(screen.getByText(en["contact.onRequest"])).toBeInTheDocument();
    expect(screen.getByText(en["contact.none"])).toBeInTheDocument();
    expect(screen.queryByText("address")).not.toBeInTheDocument();

    open("Hotel Rheinblick");
    expect(screen.getByRole("button", { name: en["connect.now"] })).toBeInTheDocument();
  });

  it("offers no connection on a card drawn from the folders, which no hub answered for", () => {
    window.matchMedia = vi.fn().mockReturnValue({ matches: true }) as never;
    const scene = sceneFor("A designer for a dataviz sprint");
    render(
      <I18nProvider>
        <GeneratedStage scene={scene!} onDetails={() => {}} />
      </I18nProvider>,
    );
    open("Lena Hofmann");
    expect(screen.queryByRole("button", { name: en["connect.ask"] })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: en["connect.now"] })).not.toBeInTheDocument();
  });

  it("says nothing about other hubs when the person searched this one only", () => {
    stage(undefined, 0);
    expect(screen.queryByText(en["reach.none"])).not.toBeInTheDocument();
    expect(screen.queryByText(/asked/)).not.toBeInTheDocument();
  });
});
