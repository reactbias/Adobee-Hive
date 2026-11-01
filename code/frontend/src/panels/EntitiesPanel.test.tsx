import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, type AdminEntity, type AdminEntityDetail, type Card, type Trust } from "../api";
import { I18nProvider } from "../i18n";
import en from "../i18n/en";
import EntitiesPanel from "./EntitiesPanel";

const RHEINBLICK: AdminEntity = {
  id: "hotel-rheinblick",
  slug: "hotel-rheinblick",
  name: "Hotel Rheinblick",
  kind: "hotel",
  claimed: true,
  rating: 4.3,
  rating_count: 7,
  published_at: "2026-10-30T09:12:00+00:00",
  version: 3,
  signature_valid: true,
  bookable: true,
  carried: true,
  removal: null,
};

const LEAD: AdminEntity = {
  ...RHEINBLICK,
  id: "w-taxi-basel",
  slug: "w-taxi-basel",
  name: "Taxi Basel",
  kind: "taxi",
  claimed: false,
  rating: null,
  rating_count: 0,
  bookable: false,
};

const TRUST: Trust = {
  signature_valid: true,
  signature: "sig",
  public_key: "Zm9vYmFyLXB1YmxpYy1rZXk",
  algorithm: "Ed25519 over canonical JSON (sorted keys, no spaces)",
  attestations: [{ claim: "dog-friendly", attested_by: "Basel Tourism" }],
  verified_reviews: { count: 7, average: 4.3, recent: [], rule: "no booking, no review" },
  freshness_days: 1,
  claimed: true,
};

const CARD: Card = {
  id: "hotel-rheinblick",
  slug: "hotel-rheinblick",
  kind: "hotel",
  name: "Hotel Rheinblick",
  tagline: "Quiet rooms over the Rhine",
  description: "Fictional seed data.",
  features: ["quiet"],
  units: [],
  version: 3,
  published_at: "2026-10-30T09:12:00+00:00",
  trust: TRUST,
};

const DETAIL: AdminEntityDetail = {
  entity: RHEINBLICK,
  card: CARD,
  offers: [{ title: "River-view double", summary: "Two guests, breakfast included" }],
  needs: [],
  contact: [
    { channel: "email", value: "stay@rheinblick.example", sharing: "public", searchable: true },
    { channel: "phone", value: "", sharing: "never", searchable: false },
  ],
  contact_sharing: { phone: "never" },
  sharing_default: "public",
  trust: TRUST,
  signature: {
    valid: true,
    signature: "sig",
    public_key: "Zm9vYmFyLXB1YmxpYy1rZXk",
    algorithm: "Ed25519 over canonical JSON (sorted keys, no spaces)",
    fresh: true,
    valid_until: "2027-01-28T09:12:00+00:00",
    version: 3,
  },
  blocked: false,
  block: null,
  carried: true,
  removal: null,
};

const REMOVAL = {
  entity_id: "hotel-rheinblick",
  reason: "asked to be taken off the hub",
  removed_at: "2026-10-31T11:00:00",
  removed_by: "session",
};

const show = () =>
  render(
    <I18nProvider>
      <EntitiesPanel />
    </I18nProvider>,
  );

describe("the entity list", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.setItem("adobee-locale", "en");
  });

  it("names every entity this hub carries, with its id and kind", async () => {
    vi.spyOn(api, "adminAudit").mockResolvedValue({ entries: [], who_limit: "one shared password" });
    vi.spyOn(api, "adminEntities").mockResolvedValue({ entities: [RHEINBLICK, LEAD], count: 2, withdrawn: 0 });
    show();

    expect(await screen.findByText("Hotel Rheinblick")).toBeInTheDocument();
    expect(screen.getByText("hotel-rheinblick · hotel")).toBeInTheDocument();
    expect(screen.getByText("Taxi Basel")).toBeInTheDocument();
    expect(screen.getByText(en["admin.entities.count"].replace("{n}", "2"))).toBeInTheDocument();
  });

  it("says claimed or unclaimed, as a word and not only a colour", async () => {
    vi.spyOn(api, "adminAudit").mockResolvedValue({ entries: [], who_limit: "one shared password" });
    vi.spyOn(api, "adminEntities").mockResolvedValue({ entities: [RHEINBLICK, LEAD], count: 2, withdrawn: 0 });
    show();

    expect(await screen.findByText(en["admin.entities.claimed"])).toBeInTheDocument();
    expect(screen.getByText(en["admin.entities.unclaimed"])).toBeInTheDocument();
  });

  it("shows a rating only when a signed receipt earned one", async () => {
    vi.spyOn(api, "adminAudit").mockResolvedValue({ entries: [], who_limit: "one shared password" });
    vi.spyOn(api, "adminEntities").mockResolvedValue({ entities: [RHEINBLICK, LEAD], count: 2, withdrawn: 0 });
    show();

    expect(
      await screen.findByText(en["admin.entities.rating"].replace("{rating}", "4.3").replace("{n}", "7")),
    ).toBeInTheDocument();
    expect(screen.getByText(en["admin.entities.noRating"])).toBeInTheDocument();
  });

  it("hands control back to the sign-in form when the session is gone", async () => {
    vi.spyOn(api, "adminEntities").mockRejectedValue(new ApiError("Missing token", 403));
    const onLost = vi.fn();
    render(
      <I18nProvider>
        <EntitiesPanel onLost={onLost} />
      </I18nProvider>,
    );

    await vi.waitFor(() => expect(onLost).toHaveBeenCalled());
  });

  it("says so when the hub carries nothing, rather than showing an empty table", async () => {
    vi.spyOn(api, "adminAudit").mockResolvedValue({ entries: [], who_limit: "one shared password" });
    vi.spyOn(api, "adminEntities").mockResolvedValue({ entities: [], count: 0, withdrawn: 0 });
    show();

    expect(await screen.findByText(en["admin.entities.empty"])).toBeInTheDocument();
  });

  it("opens one entity in full: its offers, its contact flags and its signature", async () => {
    vi.spyOn(api, "adminAudit").mockResolvedValue({ entries: [], who_limit: "one shared password" });
    vi.spyOn(api, "adminEntities").mockResolvedValue({ entities: [RHEINBLICK], count: 1, withdrawn: 0 });
    vi.spyOn(api, "adminEntity").mockResolvedValue(DETAIL);
    show();

    await userEvent.click(await screen.findByRole("button", { name: en["admin.entity.open"] }));

    expect(await screen.findByText("River-view double")).toBeInTheDocument();
    expect(screen.getByText("stay@rheinblick.example")).toBeInTheDocument();
    expect(screen.getByText(en["admin.sharing.public"])).toBeInTheDocument();
    expect(screen.getByText(DETAIL.signature.public_key)).toBeInTheDocument();
    expect(screen.getByText(en["trust.signed"])).toBeInTheDocument();
    expect(screen.getByText(en["admin.entity.notBlocked"])).toBeInTheDocument();
  });

  it("does not list a channel the card publishes nothing for", async () => {
    vi.spyOn(api, "adminAudit").mockResolvedValue({ entries: [], who_limit: "one shared password" });
    vi.spyOn(api, "adminEntities").mockResolvedValue({ entities: [RHEINBLICK], count: 1, withdrawn: 0 });
    vi.spyOn(api, "adminEntity").mockResolvedValue(DETAIL);
    show();

    await userEvent.click(await screen.findByRole("button", { name: en["admin.entity.open"] }));
    await screen.findByText("stay@rheinblick.example");
    expect(screen.queryByText("phone")).not.toBeInTheDocument();
  });

  it("says a blocked entity is blocked, and why, where the operator decides", async () => {
    vi.spyOn(api, "adminAudit").mockResolvedValue({ entries: [], who_limit: "one shared password" });
    vi.spyOn(api, "adminEntities").mockResolvedValue({ entities: [RHEINBLICK], count: 1, withdrawn: 0 });
    vi.spyOn(api, "adminEntity").mockResolvedValue({
      ...DETAIL,
      blocked: true,
      block: {
        kind: "entity",
        subject: "hotel-rheinblick",
        reason: "fabricated reviews",
        added_at: "2026-10-31T10:00:00",
        added_by: "admin",
      },
    });
    show();

    await userEvent.click(await screen.findByRole("button", { name: en["admin.entity.open"] }));
    expect(await screen.findByText(en["admin.entity.isBlocked"])).toBeInTheDocument();
    expect(
      screen.getByText(en["admin.entity.blockedWhy"].replace("{reason}", "fabricated reviews")),
    ).toBeInTheDocument();
  });

  it("goes back to the list", async () => {
    vi.spyOn(api, "adminAudit").mockResolvedValue({ entries: [], who_limit: "one shared password" });
    vi.spyOn(api, "adminEntities").mockResolvedValue({ entities: [RHEINBLICK], count: 1, withdrawn: 0 });
    vi.spyOn(api, "adminEntity").mockResolvedValue(DETAIL);
    show();

    await userEvent.click(await screen.findByRole("button", { name: en["admin.entity.open"] }));
    await userEvent.click(await screen.findByRole("button", { name: en["admin.entity.back"] }));
    expect(await screen.findByText(en["admin.entities.lead"])).toBeInTheDocument();
  });

  it("says what a removal will do, and names the entity, before it does it", async () => {
    vi.spyOn(api, "adminEntities").mockResolvedValue({ entities: [RHEINBLICK], count: 1, withdrawn: 0 });
    vi.spyOn(api, "adminEntity").mockResolvedValue(DETAIL);
    const remove = vi.spyOn(api, "adminRemoveEntity").mockResolvedValue({
      entity_id: "hotel-rheinblick",
      carried: false,
      history_kept: true,
    });
    show();

    await userEvent.click(await screen.findByRole("button", { name: en["admin.entity.open"] }));
    await userEvent.click(await screen.findByRole("button", { name: en["admin.remove.button"] }));

    expect(screen.getByText(en["admin.remove.confirm"].replace("{name}", "Hotel Rheinblick"))).toBeInTheDocument();
    expect(screen.getByText(en["admin.remove.will"])).toBeInTheDocument();
    expect(screen.getByText(en["admin.remove.notBlock"])).toBeInTheDocument();
    expect(remove).not.toHaveBeenCalled();
  });

  it("will not remove without a reason, and sends the reason when there is one", async () => {
    vi.spyOn(api, "adminEntities").mockResolvedValue({ entities: [RHEINBLICK], count: 1, withdrawn: 0 });
    vi.spyOn(api, "adminEntity").mockResolvedValue(DETAIL);
    const remove = vi.spyOn(api, "adminRemoveEntity").mockResolvedValue({
      entity_id: "hotel-rheinblick",
      carried: false,
      history_kept: true,
    });
    show();

    await userEvent.click(await screen.findByRole("button", { name: en["admin.entity.open"] }));
    await userEvent.click(await screen.findByRole("button", { name: en["admin.remove.button"] }));
    expect(screen.getByRole("button", { name: en["admin.remove.do"] })).toBeDisabled();
    expect(screen.getByText(en["admin.remove.reasonNeeded"])).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText(en["admin.remove.reason"]), "asked to be taken off");
    await userEvent.click(screen.getByRole("button", { name: en["admin.remove.do"] }));

    expect(remove).toHaveBeenCalledWith("hotel-rheinblick", "asked to be taken off");
  });

  it("cancels without touching anything", async () => {
    vi.spyOn(api, "adminEntities").mockResolvedValue({ entities: [RHEINBLICK], count: 1, withdrawn: 0 });
    vi.spyOn(api, "adminEntity").mockResolvedValue(DETAIL);
    const remove = vi.spyOn(api, "adminRemoveEntity");
    show();

    await userEvent.click(await screen.findByRole("button", { name: en["admin.entity.open"] }));
    await userEvent.click(await screen.findByRole("button", { name: en["admin.remove.button"] }));
    await userEvent.click(screen.getByRole("button", { name: en["admin.remove.cancel"] }));

    expect(remove).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: en["admin.remove.button"] })).toBeInTheDocument();
  });

  it("offers to carry a removed entity again, and says why it was removed", async () => {
    const gone = { ...RHEINBLICK, carried: false, removal: REMOVAL };
    vi.spyOn(api, "adminEntities").mockResolvedValue({ entities: [gone], count: 0, withdrawn: 1 });
    vi.spyOn(api, "adminEntity").mockResolvedValue({
      ...DETAIL,
      entity: gone,
      carried: false,
      removal: REMOVAL,
    });
    show();

    expect(await screen.findByText(en["admin.remove.removed"])).toBeInTheDocument();
    await userEvent.click(await screen.findByRole("button", { name: en["admin.entity.open"] }));

    expect(await screen.findByText(en["admin.remove.why"].replace("{reason}", REMOVAL.reason))).toBeInTheDocument();
    expect(screen.getByRole("button", { name: en["admin.restore.button"] })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: en["admin.remove.button"] })).not.toBeInTheDocument();
  });

  it("says removing and blocking are not the same act, where the operator chooses", async () => {
    vi.spyOn(api, "adminEntities").mockResolvedValue({ entities: [RHEINBLICK], count: 1, withdrawn: 0 });
    vi.spyOn(api, "adminEntity").mockResolvedValue(DETAIL);
    show();

    await userEvent.click(await screen.findByRole("button", { name: en["admin.entity.open"] }));
    await userEvent.click(await screen.findByRole("button", { name: en["admin.block.button"] }));

    expect(screen.getByText(en["admin.block.will"])).toBeInTheDocument();
    expect(screen.getByText(en["admin.block.notRemove"])).toBeInTheDocument();
  });

  it("shows who changed this entity, when and why, and what the ledger cannot prove", async () => {
    vi.spyOn(api, "adminEntities").mockResolvedValue({ entities: [RHEINBLICK], count: 1, withdrawn: 0 });
    vi.spyOn(api, "adminEntity").mockResolvedValue(DETAIL);
    vi.spyOn(api, "adminAudit").mockResolvedValue({
      entries: [
        {
          id: "a1",
          at: "2026-10-31T11:00:00",
          action: "entity.remove",
          subject: "hotel-rheinblick",
          reason: "asked to be taken off",
          actor: "admin",
          credential: "session",
          detail: "",
        },
      ],
      who_limit: "one shared password",
    });
    show();

    await userEvent.click(await screen.findByRole("button", { name: en["admin.entity.open"] }));
    expect(await screen.findByText("asked to be taken off")).toBeInTheDocument();
    expect(screen.getByText(en["admin.ledger.whoLimit"])).toBeInTheDocument();
  });
});
