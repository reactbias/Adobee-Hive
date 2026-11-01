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

  it("asks for the owner token when the hub requires one, then tries again", async () => {
    vi.spyOn(api, "connections").mockResolvedValue({
      awaiting_rating: [],
      awaiting_confirmation: [requested("cx-1", "traveller-ab12")],
    });
    const confirm = vi
      .spyOn(api, "confirmConnection")
      .mockRejectedValueOnce(new Error("confirm on cx-1 needs authority. This hub accepts: this hub's X-Owner-Token"))
      .mockResolvedValueOnce({ ...requested("cx-1", "traveller-ab12"), state: "open" });
    draw();

    fireEvent.click(await screen.findByRole("button", { name: en["requests.accept"] }));
    expect(await screen.findByText(en["owner.tokenNeeded"])).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText(en["owner.token"]), { target: { value: "fictional-token" } });
    fireEvent.click(screen.getByRole("button", { name: en["owner.useToken"] }));
    expect(screen.queryByText(en["owner.tokenNeeded"])).not.toBeInTheDocument();
    expect(sessionStorage.getItem("adobee-owner-token")).toBe("fictional-token");

    fireEvent.click(screen.getByRole("button", { name: en["requests.accept"] }));
    expect(await screen.findByText(en["requests.accepted"])).toBeInTheDocument();
    expect(confirm).toHaveBeenCalledTimes(2);
  });

  it("does not ask for a token the hub's operator never set", async () => {
    vi.spyOn(api, "connections").mockResolvedValue({
      awaiting_rating: [],
      awaiting_confirmation: [requested("cx-1", "traveller-ab12")],
    });
    vi.spyOn(api, "confirmConnection").mockRejectedValue(
      new Error("This hub accepts: this hub's X-Owner-Token, which its operator has not set"),
    );
    draw();

    fireEvent.click(await screen.findByRole("button", { name: en["requests.accept"] }));
    expect(await screen.findByText(/which its operator has not set/)).toBeInTheDocument();
    expect(screen.queryByPlaceholderText(en["owner.token"])).not.toBeInTheDocument();
  });

  it("draws nothing while nobody is waiting, so the owner's page carries no empty headings", async () => {
    const read = vi.spyOn(api, "connections").mockResolvedValue({ awaiting_rating: [], awaiting_confirmation: [] });
    draw();
    await vi.waitFor(() => expect(read).toHaveBeenCalled());
    expect(screen.queryByRole("heading", { name: en["requests.title"] })).not.toBeInTheDocument();
  });

  // Changed from "draws nothing when the hub cannot say": silence read as "nobody wants to meet you", which is
  // a different and worse claim than "we could not ask". #169.
  it("says it could not ask, rather than letting a failed read read as nobody waiting", async () => {
    const read = vi.spyOn(api, "connections").mockRejectedValue(new Error("404 Not Found"));
    draw();
    expect(await screen.findByText(en["requests.unreachable"])).toBeInTheDocument();
    expect(read).toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: en["requests.accept"] })).not.toBeInTheDocument();
  });

  it("counts who is waiting in the heading", async () => {
    vi.spyOn(api, "connections").mockResolvedValue({
      awaiting_rating: [],
      awaiting_confirmation: [requested("cx-1", "traveller-ab12"), requested("cx-2", "traveller-cd34")],
    });
    draw();
    expect(await screen.findByRole("heading", { name: en["requests.count"].replace("{n}", "2") })).toBeInTheDocument();
  });

  it("asks again on its own and marks a request that was not there before as new", async () => {
    vi.useFakeTimers();
    const read = vi
      .spyOn(api, "connections")
      .mockResolvedValue({ awaiting_rating: [], awaiting_confirmation: [requested("cx-1", "traveller-ab12")] });
    draw();
    await vi.waitFor(() => expect(screen.getByText(/traveller-ab12/)).toBeInTheDocument());
    expect(screen.queryByText(en["requests.new"])).not.toBeInTheDocument();

    read.mockResolvedValue({
      awaiting_rating: [],
      awaiting_confirmation: [requested("cx-1", "traveller-ab12"), requested("cx-2", "traveller-cd34")],
    });
    await vi.advanceTimersByTimeAsync(30_000);
    await vi.waitFor(() => expect(screen.getByText(/traveller-cd34/)).toBeInTheDocument());
    // Only the one that arrived while the owner was looking is new; the one already there is not.
    expect(screen.getAllByText(en["requests.new"])).toHaveLength(1);
    expect(screen.getByText(/traveller-cd34/)).toHaveTextContent(en["requests.new"]);
    vi.useRealTimers();
  });

  it("keeps an answer on screen after the hub has dropped the row from its waiting list", async () => {
    vi.useFakeTimers();
    const read = vi
      .spyOn(api, "connections")
      .mockResolvedValue({ awaiting_rating: [], awaiting_confirmation: [requested("cx-1", "traveller-ab12")] });
    vi.spyOn(api, "confirmConnection").mockResolvedValue({ ...requested("cx-1", "traveller-ab12"), state: "open" });
    draw();
    await vi.waitFor(() => expect(screen.getByRole("button", { name: en["requests.accept"] })).toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: en["requests.accept"] }));
    await vi.waitFor(() => expect(screen.getByText(en["requests.accepted"])).toBeInTheDocument());

    read.mockResolvedValue({ awaiting_rating: [], awaiting_confirmation: [] });
    await vi.advanceTimersByTimeAsync(30_000);
    expect(screen.getByText(en["requests.accepted"])).toBeInTheDocument();
    vi.useRealTimers();
  });
});
