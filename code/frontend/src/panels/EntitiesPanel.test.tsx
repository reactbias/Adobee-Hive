import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, type AdminEntity } from "../api";
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
    vi.spyOn(api, "adminEntities").mockResolvedValue({ entities: [RHEINBLICK, LEAD], count: 2 });
    show();

    expect(await screen.findByText("Hotel Rheinblick")).toBeInTheDocument();
    expect(screen.getByText("hotel-rheinblick · hotel")).toBeInTheDocument();
    expect(screen.getByText("Taxi Basel")).toBeInTheDocument();
    expect(screen.getByText(en["admin.entities.count"].replace("{n}", "2"))).toBeInTheDocument();
  });

  it("says claimed or unclaimed, as a word and not only a colour", async () => {
    vi.spyOn(api, "adminEntities").mockResolvedValue({ entities: [RHEINBLICK, LEAD], count: 2 });
    show();

    expect(await screen.findByText(en["admin.entities.claimed"])).toBeInTheDocument();
    expect(screen.getByText(en["admin.entities.unclaimed"])).toBeInTheDocument();
  });

  it("shows a rating only when a signed receipt earned one", async () => {
    vi.spyOn(api, "adminEntities").mockResolvedValue({ entities: [RHEINBLICK, LEAD], count: 2 });
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
    vi.spyOn(api, "adminEntities").mockResolvedValue({ entities: [], count: 0 });
    show();

    expect(await screen.findByText(en["admin.entities.empty"])).toBeInTheDocument();
  });
});
