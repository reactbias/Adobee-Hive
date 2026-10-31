import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, type Connection } from "../api";
import { I18nProvider } from "../i18n";
import en from "../i18n/en";
import ConnectionRequests from "./ConnectionRequests";

const requested = (id: string, requester: string): Connection => ({
  id,
  created_at: "2026-10-31T10:00:00",
  state: "requested",
  requester,
  requester_hub: "basel",
  target: "lena-hofmann",
  target_hub: "",
  via_hub: "",
  sharing: "confirm",
  published_rating: null,
  opened_at: null,
  stale_at: "2026-11-07T10:00:00",
  rated_at: null,
  rating: null,
  note: null,
  rating_stars: null,
  published_rating_stars: null,
});

function draw() {
  render(
    <I18nProvider>
      <ConnectionRequests target="lena-hofmann" />
    </I18nProvider>,
  );
}

describe("requests waiting on the owner's yes", () => {
  beforeEach(() => localStorage.setItem("adobee-locale", "en"));
  afterEach(() => vi.restoreAllMocks());

  it("lists who asked for this entity, and lets the owner accept or decline each one", async () => {
    const read = vi.spyOn(api, "connections").mockResolvedValue({
      awaiting_rating: [],
      awaiting_confirmation: [requested("cx-1", "traveller-ab12"), requested("cx-2", "traveller-cd34")],
    });
    const confirm = vi.spyOn(api, "confirmConnection").mockResolvedValue({
      ...requested("cx-1", "traveller-ab12"),
      state: "open",
    });
    const decline = vi.spyOn(api, "declineConnection").mockResolvedValue({
      ...requested("cx-2", "traveller-cd34"),
      state: "declined",
    });
    draw();

    expect(await screen.findByText(en["requests.from"].replace("{who}", "traveller-ab12"))).toBeInTheDocument();
    expect(read).toHaveBeenCalledWith({ target: "lena-hofmann" });
    const [accept] = screen.getAllByRole("button", { name: en["requests.accept"] });
    fireEvent.click(accept);
    expect(await screen.findByText(en["requests.accepted"])).toBeInTheDocument();
    expect(confirm).toHaveBeenCalledWith("cx-1");

    fireEvent.click(screen.getByRole("button", { name: en["requests.decline"] }));
    expect(await screen.findByText(en["requests.refused"])).toBeInTheDocument();
    expect(decline).toHaveBeenCalledWith("cx-2");
    expect(screen.queryByRole("button", { name: en["requests.accept"] })).not.toBeInTheDocument();
  });

  it("says nobody is waiting rather than showing an empty list", async () => {
    vi.spyOn(api, "connections").mockResolvedValue({ awaiting_rating: [], awaiting_confirmation: [] });
    draw();
    expect(await screen.findByText(en["requests.empty"])).toBeInTheDocument();
  });

  it("draws nothing when the hub cannot say", async () => {
    const read = vi.spyOn(api, "connections").mockRejectedValue(new Error("404 Not Found"));
    draw();
    await vi.waitFor(() => expect(read).toHaveBeenCalled());
    expect(screen.queryByRole("heading", { name: en["requests.title"] })).not.toBeInTheDocument();
  });
});
