import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "../i18n";
import en from "../i18n/en";
import { sceneFor, sceneFromDiscovery, type Scene } from "../lib/cardView";
import GeneratedStage from "./GeneratedStage";

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

  it("goes on after the yes: the next steps, then the rating, then the score the person gave", () => {
    vi.useFakeTimers();
    const onDetails = vi.fn();
    const scene = sceneFor(en["agent.example.1"]);
    render(
      <I18nProvider>
        <GeneratedStage scene={scene!} onDetails={onDetails} />
      </I18nProvider>,
    );
    open("Hotel Krafft Basel");
    beat();
    fireEvent.click(screen.getByRole("button", { name: /Room reservation/ }));
    for (let i = 0; i < 6 && !screen.queryByRole("button", { name: en["card.yes"] }); i += 1) beat();

    fireEvent.click(screen.getByRole("button", { name: en["card.yes"] }));
    expect(screen.queryByText(en["card.yes.done"])).not.toBeInTheDocument();
    beat();
    expect(screen.getByText(en["card.yes.done"])).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: en["card.next.agent"] })).not.toBeInTheDocument();

    beat();
    expect(screen.getByText(en["card.next.title"])).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: en["card.next.agent"] }));
    expect(onDetails).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("radiogroup", { name: en["card.rate.ask"] })).not.toBeInTheDocument();

    beat();
    fireEvent.click(screen.getByRole("radio", { name: "4" }));
    expect(screen.queryByText("4.0 / 5")).not.toBeInTheDocument();
    beat();
    expect(screen.getByText("4.0 / 5")).toBeInTheDocument();
    expect(screen.getByText(en["card.rate.yours"])).toBeInTheDocument();
  });

  it("lets the person step back from a yes to the other offerings", () => {
    window.matchMedia = vi.fn().mockReturnValue({ matches: true }) as never;
    const scene = sceneFor(en["agent.example.1"]);
    render(
      <I18nProvider>
        <GeneratedStage scene={scene!} onDetails={() => {}} />
      </I18nProvider>,
    );
    open("Hotel Krafft Basel");
    fireEvent.click(screen.getByRole("button", { name: /Room reservation/ }));
    fireEvent.click(screen.getByRole("button", { name: en["card.yes"] }));

    fireEvent.click(screen.getByRole("button", { name: en["card.next.other"] }));
    expect(screen.queryByText(en["card.yes.done"])).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Room reservation/ })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("button", { name: /Small event on the Rhine terrace/ })).toBeInTheDocument();
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

  it("says nothing about other hubs when the person searched this one only", () => {
    stage(undefined, 0);
    expect(screen.queryByText(en["reach.none"])).not.toBeInTheDocument();
    expect(screen.queryByText(/asked/)).not.toBeInTheDocument();
  });
});
