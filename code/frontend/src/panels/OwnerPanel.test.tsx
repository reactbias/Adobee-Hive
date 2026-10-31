import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, type Card, type OwnerOverview, type Proposal } from "../api";
import { I18nProvider } from "../i18n";
import de from "../i18n/de";
import en from "../i18n/en";
import it_ from "../i18n/it";
import OwnerPanel from "./OwnerPanel";

// The business chapter is the owner's dashboard: the change box in the brief, like the chat's input; the bookings,
// what agents asked for and the signed card in the panel; the city's demand map one tab away. api.ts is mocked.

const TRUST = { signature_valid: true, attestations: [], verified_reviews: { count: 0, average: null } };
const CARD = {
  id: "hotel-rheinblick",
  slug: "rheinblick",
  name: "Hotel Rheinblick",
  version: 1,
  units: [],
  features: [],
  trust: TRUST,
} as unknown as Card;

const OVERVIEW: OwnerOverview = {
  card: CARD,
  bookings: [
    {
      id: "b1",
      unit_id: "u1",
      guest_name: "Mara Keller",
      check_in: "2026-11-13",
      check_out: "2026-11-15",
      total_chf: 256,
      status: "confirmed",
      agent: "a",
    },
  ],
  handoffs: [],
  missed_demand: [{ detail: "missing sauna (asked: sauna, quiet)", times: 3 }],
  last_7_days: { shown: 4, read: 3, booked: 1, explore_handoff: 1 },
  waiting: {
    agents: 2,
    budget_chf: 1750,
    asks: [{ missing: ["vegan breakfast"], cheaper: false, agents: 2, budget_chf: 1750 }],
    offers_sent: 0,
  },
};

const PROPOSAL: Proposal = {
  card_id: "hotel-rheinblick",
  proposed: CARD,
  changes: [{ field: "features", before: [], after: ["vegan breakfast"] }],
  summary: "Mock mode: added vegan breakfast",
  summary_items: [
    { code: "added", tag: "vegan breakfast" },
    { code: "price", unit: "Courtyard double", price_chf: 165 },
  ],
  mode: "mock",
};

const TAXI = {
  ...CARD,
  id: "x-taxi",
  name: "Taxi Zentrale Basel",
  trust: { ...TRUST, claimed: false },
} as unknown as Card;
const TAXI_OVERVIEW: OwnerOverview = {
  ...OVERVIEW,
  card: TAXI,
  bookings: [],
  handoffs: [{ item: "Advice meeting", created_at: "2026-10-31T08:00:00Z" }],
  missed_demand: [],
  last_7_days: { shown: 7, explore_handoff: 1 },
  waiting: { agents: 0, budget_chf: 0, asks: [], offers_sent: 0 },
};

function setup(locale: string) {
  localStorage.setItem("adobee-locale", locale);
  vi.spyOn(api, "cards").mockResolvedValue([CARD, TAXI]);
  vi.spyOn(api, "owner").mockImplementation(async (id: string) => (id === "x-taxi" ? TAXI_OVERVIEW : OVERVIEW));
  vi.spyOn(api, "demand").mockResolvedValue({
    days: 7,
    searches: 46,
    unserved_searches: 26,
    features: [{ feature: "vegan breakfast", asked: 8, unserved: 8, unserved_share: 1 }],
  });
  render(
    <I18nProvider>
      <OwnerPanel />
    </I18nProvider>,
  );
  return userEvent.setup();
}

describe("the business chapter", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("opens on the owner's dashboard, with the booking that arrived", async () => {
    setup("en");
    expect(screen.getByRole("tab", { name: en["business.tab.owner"] })).toHaveAttribute("aria-selected", "true");
    expect(await screen.findByText("Mara Keller")).toBeInTheDocument();
    expect(screen.getByText(en["chapter.business.lead"].replace("{name}", "Hotel Rheinblick"))).toBeInTheDocument();
  });

  it("counts what agents did with this card: shown, read, booked or handed off", async () => {
    setup("en");
    const kpis = await screen.findByRole("group", { name: en["owner.week.title"] });
    expect(within(kpis).getByText(en["owner.week.read"]).previousSibling).toHaveTextContent("3");
    expect(within(kpis).getByText(en["owner.week.booked"]).previousSibling).toHaveTextContent("2");
  });

  it("shows no counters while every count is zero: a fresh card reads as fresh, not as failing", async () => {
    localStorage.setItem("adobee-locale", "en");
    vi.spyOn(api, "cards").mockResolvedValue([CARD]);
    vi.spyOn(api, "owner").mockResolvedValue({ ...OVERVIEW, last_7_days: {} });
    vi.spyOn(api, "demand").mockRejectedValue(new Error("offline"));
    render(
      <I18nProvider>
        <OwnerPanel />
      </I18nProvider>,
    );
    await screen.findByText("Mara Keller");
    expect(screen.queryByRole("group", { name: en["owner.week.title"] })).not.toBeInTheDocument();
  });

  it("lists every business in the Hive, unclaimed ones too, and shows the one picked", async () => {
    const user = setup("en");
    await screen.findByText("Mara Keller");
    await user.selectOptions(screen.getByRole("combobox", { name: en["owner.business"] }), "x-taxi");
    expect(
      await screen.findByText(en["chapter.business.leadUnclaimed"].replace("{name}", "Taxi Zentrale Basel")),
    ).toBeInTheDocument();
    const kpis = screen.getByRole("group", { name: en["owner.week.title"] });
    expect(within(kpis).getByText(en["owner.week.shown"]).previousSibling).toHaveTextContent("7");
    // Nobody has claimed it, so there is nothing to edit: a line says so instead of the change box.
    expect(screen.queryByRole("textbox", { name: en["owner.change"] })).not.toBeInTheDocument();
    expect(screen.getByText(en["owner.unclaimed"])).toBeInTheDocument();
  });

  it("shows a business without rooms what agents handed off to its site, not an empty bookings table", async () => {
    const user = setup("de");
    await screen.findByText("Mara Keller");
    await user.selectOptions(screen.getByRole("combobox", { name: de["owner.business"] }), "x-taxi");
    expect(await screen.findByRole("heading", { name: de["owner.handoffs.title"] })).toBeInTheDocument();
    expect(screen.getByText("Advice meeting")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: de["owner.bookings.title"] })).not.toBeInTheDocument();
    const kpis = screen.getByRole("group", { name: de["owner.week.title"] });
    expect(within(kpis).getByText(de["owner.week.handedOff"]).previousSibling).toHaveTextContent("1");
  });

  it("puts what agents asked for in one list, waiting first, with a Use for each", async () => {
    setup("en");
    const list = await screen.findByRole("list", { name: en["owner.asked.title"] });
    expect(within(list).getByText("vegan breakfast")).toBeInTheDocument();
    expect(within(list).getByText("sauna")).toBeInTheDocument();
    expect(within(list).getAllByRole("button", { name: en["owner.waiting.use"] })).toHaveLength(2);
  });

  it("turns a plain sentence into a diff, then signs and shows the new version", async () => {
    const propose = vi.spyOn(api, "propose").mockResolvedValue(PROPOSAL);
    const publish = vi.spyOn(api, "publish").mockResolvedValue({ ...CARD, version: 2 });
    const user = setup("en");
    await screen.findByText("Mara Keller");

    const box = screen.getByRole("textbox", { name: en["owner.change"] });
    await user.clear(box);
    await user.type(box, "add vegan breakfast{Enter}");
    expect(propose).toHaveBeenCalledWith("hotel-rheinblick", "add vegan breakfast");
    expect(await screen.findByText("vegan breakfast", { selector: ".diff-after" })).toBeInTheDocument();

    vi.mocked(api.owner).mockResolvedValue({
      ...OVERVIEW,
      card: { ...CARD, version: 2 },
      waiting: { ...OVERVIEW.waiting, offers_sent: 2 },
    });
    await user.click(screen.getByRole("button", { name: en["owner.publish"] }));
    expect(publish).toHaveBeenCalled();
    expect(
      await screen.findByText(en["owner.publishedOffers"].replace("{version}", "2").replace("{n}", "2")),
    ).toBeInTheDocument();
    expect(screen.getByText("v2")).toBeInTheDocument();
  });

  it("opens with an empty box: a hint in the owner's voice, never another business's change", async () => {
    const user = setup("de");
    await screen.findByText("Mara Keller");
    const box = screen.getByRole("textbox", { name: de["owner.change"] });
    expect(box).toHaveValue("");
    expect(box).toHaveAttribute("placeholder", de["owner.placeholder"]);
    // The button names what it shows: the next signed version of this card, not yet live.
    expect(screen.getByRole("button", { name: de["owner.previewVersion"].replace("{version}", "2") })).toBeDisabled();
    await user.type(box, "Ab heute Frühstück inklusive");
    await user.selectOptions(screen.getByRole("combobox", { name: de["owner.business"] }), "x-taxi");
    await user.selectOptions(screen.getByRole("combobox", { name: de["owner.business"] }), "hotel-rheinblick");
    expect(await screen.findByRole("textbox", { name: de["owner.change"] })).toHaveValue("");
  });

  it("Use writes the command in the page's language and previews it at once", async () => {
    const propose = vi.spyOn(api, "propose").mockResolvedValue(PROPOSAL);
    const user = setup("de");
    await user.click((await screen.findAllByRole("button", { name: de["owner.waiting.use"] }))[0]);
    expect(screen.getByRole("textbox", { name: de["owner.change"] })).toHaveValue("vegan breakfast hinzufügen");
    expect(propose).toHaveBeenCalledWith("hotel-rheinblick", "vegan breakfast hinzufügen");
    expect(await screen.findByRole("button", { name: de["owner.publish"] })).toBeInTheDocument();
  });

  it("words the offline summary in the page's language", async () => {
    const propose = vi.spyOn(api, "propose").mockResolvedValue(PROPOSAL);
    const user = setup("it");
    await user.click((await screen.findAllByRole("button", { name: it_["owner.waiting.use"] }))[0]);
    expect(propose).toHaveBeenCalledWith("hotel-rheinblick", "aggiungi vegan breakfast");
    expect(await screen.findByText(/Aggiunto: vegan breakfast/)).toBeInTheDocument();
    expect(screen.queryByText(/Mock mode/)).not.toBeInTheDocument();
  });

  it("shows the city's demand map one tab away, without presenter tools", async () => {
    const user = setup("en");
    await user.click(screen.getByRole("tab", { name: en["business.tab.demand"] }));
    expect(await screen.findByText("46")).toBeInTheDocument();
    expect(screen.queryByText("most unserved request")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: en["demand.simulate"] })).not.toBeInTheDocument();
  });

  it("shows the owner that a forged copy of the card is rejected (presenters, ?demo)", async () => {
    window.history.replaceState(null, "", "/?demo");
    vi.spyOn(api, "forge").mockResolvedValue(CARD);
    vi.spyOn(api, "verify")
      .mockResolvedValueOnce({ signature_valid: true })
      .mockResolvedValueOnce({ signature_valid: false })
      .mockResolvedValueOnce({ signature_valid: false });
    const user = setup("en");

    await user.click(await screen.findByRole("button", { name: en["card.tamper.perk"] }));

    expect(await screen.findByText(en["card.tamper.valid"])).toBeInTheDocument();
    expect(screen.getAllByText(en["card.tamper.rejected"])).toHaveLength(2);
  });
});
