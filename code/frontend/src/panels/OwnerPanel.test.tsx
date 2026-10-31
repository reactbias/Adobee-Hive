import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, type Card, type OwnerOverview, type Proposal } from "../api";
import { I18nProvider } from "../i18n";
import de from "../i18n/de";
import en from "../i18n/en";
import it_ from "../i18n/it";
import OwnerPanel from "./OwnerPanel";

// The owner studio speaks the page's language even offline: the Use button writes a command in that language and the
// offline summary is worded from items, not from the backend's English sentence. api.ts is mocked.

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
  bookings: [],
  missed_demand: [],
  last_7_days: {},
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

function setup(locale: string) {
  localStorage.setItem("adobee-locale", locale);
  vi.spyOn(api, "cards").mockResolvedValue([CARD]);
  vi.spyOn(api, "owner").mockResolvedValue(OVERVIEW);
  render(
    <I18nProvider>
      <OwnerPanel />
    </I18nProvider>,
  );
  return userEvent.setup();
}

describe("owner studio in every language", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("Use writes the command in the page's language", async () => {
    const user = setup("de");
    await user.click(await screen.findByRole("button", { name: de["owner.waiting.use"] }));
    expect(screen.getByRole("textbox")).toHaveValue("vegan breakfast hinzufügen");
  });

  it("words the offline summary in the page's language", async () => {
    const propose = vi.spyOn(api, "propose").mockResolvedValue(PROPOSAL);
    const user = setup("it");
    await user.click(await screen.findByRole("button", { name: it_["owner.waiting.use"] }));
    expect(screen.getByRole("textbox")).toHaveValue("aggiungi vegan breakfast");
    await user.click(screen.getByRole("button", { name: it_["owner.preview"] }));
    expect(propose).toHaveBeenCalledWith("hotel-rheinblick", "aggiungi vegan breakfast");
    expect(await screen.findByText(/Aggiunto: vegan breakfast/)).toBeInTheDocument();
    expect(screen.queryByText(/Mock mode/)).not.toBeInTheDocument();
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

  it("says plainly whose side this is", async () => {
    setup("en");
    expect(await screen.findByText(en["owner.role"].replace("{name}", "Hotel Rheinblick"))).toBeInTheDocument();
  });
});
