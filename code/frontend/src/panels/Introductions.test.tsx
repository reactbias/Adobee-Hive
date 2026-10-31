import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, type Connection } from "../api";
import { I18nProvider } from "../i18n";
import en from "../i18n/en";
import { remember } from "../lib/connect";
import Introductions from "./Introductions";

const open = (over: Partial<Connection> = {}): Connection => ({
  id: "cx-1",
  created_at: "2026-10-31T10:00:00",
  state: "open",
  requester: "traveller-ab12",
  requester_hub: "basel",
  target: "pension-limmat",
  target_hub: "zurich",
  via_hub: "zurich",
  sharing: "public",
  published_rating: 50,
  opened_at: "2026-10-31T10:00:00",
  stale_at: "2099-11-30T10:00:00",
  rated_at: null,
  rating: null,
  note: null,
  rating_stars: null,
  published_rating_stars: 5,
  ...over,
});

function draw() {
  render(
    <I18nProvider>
      <Introductions />
    </I18nProvider>,
  );
}

describe("how did it go", () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem("adobee-locale", "en");
    localStorage.setItem("adobee-requester", "traveller-ab12");
    remember("pension-limmat", "Pension Limmat");
  });
  afterEach(() => vi.restoreAllMocks());

  it("stays out of the way when nothing is waiting for a score", async () => {
    const read = vi.spyOn(api, "connections").mockResolvedValue({ awaiting_rating: [], awaiting_confirmation: [] });
    draw();
    await vi.waitFor(() => expect(read).toHaveBeenCalledWith({ requester: "traveller-ab12" }));
    expect(screen.queryByRole("heading", { name: en["score.title"] })).not.toBeInTheDocument();
  });

  it("asks by name with the deadline visible, scores in tenths of a star, once, and shows what it did", async () => {
    vi.spyOn(api, "connections").mockResolvedValue({ awaiting_rating: [open()], awaiting_confirmation: [] });
    const score = vi.spyOn(api, "score").mockResolvedValue({
      connection: open({ state: "rated", rating: 25, rating_stars: 2.5 }),
      hub: "zurich",
      gap: 25,
      gap_stars: 2.5,
      says: "zurich promised 5.0 and you found 2.5",
      hub_standing: {
        hub: "zurich",
        error: 25,
        error_stars: 2.5,
        evidence: 4,
        verdict: "over-promises",
        why: "over-promised by 2.5 stars over 4 introductions",
      },
    });
    draw();

    expect(await screen.findByRole("heading", { name: "How did it go with Pension Limmat?" })).toBeInTheDocument();
    expect(screen.getByText(/You can score this until .*2099/)).toBeInTheDocument();
    const send = screen.getByRole("button", { name: en["score.send"] });
    expect(send).toBeDisabled();

    const slider = screen.getByRole("slider", { name: en["score.label"] });
    expect(slider).toHaveAttribute("max", "50");
    expect(slider).toHaveAttribute("step", "1");
    fireEvent.change(slider, { target: { value: "25" } });
    expect(screen.getByText("2.5 / 5")).toBeInTheDocument();
    fireEvent.click(send);

    expect(await screen.findByText("Thank you. zurich promised 5.0 and you found 2.5.")).toBeInTheDocument();
    expect(score).toHaveBeenCalledWith("cx-1", 25);
    // Lower error is better: a hub that published more than people found reads as over-promising.
    expect(screen.getByText(en["finder.cal.over"].replace("{stars}", "2.5"))).toBeInTheDocument();
    expect(screen.queryByRole("slider")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: en["score.send"] })).not.toBeInTheDocument();
  });

  it("says plainly when an introduction went stale, and stops asking", async () => {
    vi.spyOn(api, "connections").mockResolvedValue({
      awaiting_rating: [open({ stale_at: "2020-01-01T00:00:00" })],
      awaiting_confirmation: [],
    });
    draw();
    expect(await screen.findByText(en["score.stale"])).toBeInTheDocument();
    expect(screen.queryByRole("slider")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: en["score.send"] })).not.toBeInTheDocument();
  });

  it("stops asking when the hub says the moment has passed", async () => {
    vi.spyOn(api, "connections").mockResolvedValue({ awaiting_rating: [open()], awaiting_confirmation: [] });
    vi.spyOn(api, "score").mockRejectedValue(
      new Error("this connection went unscored for 30 days and is closed; it cannot be scored now"),
    );
    draw();
    fireEvent.change(await screen.findByRole("slider"), { target: { value: "40" } });
    fireEvent.click(screen.getByRole("button", { name: en["score.send"] }));
    expect(await screen.findByText(en["score.stale"])).toBeInTheDocument();
    expect(screen.queryByRole("slider")).not.toBeInTheDocument();
  });
});
