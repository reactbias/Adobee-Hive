import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, type Connection } from "../api";
import { I18nProvider } from "../i18n";
import en from "../i18n/en";
import Connect from "./Connect";

const row = (state: Connection["state"]): Connection => ({
  id: "cx-1",
  created_at: "2026-10-31T10:00:00",
  state,
  requester: "traveller-ab12",
  requester_hub: "basel",
  target: "lena-hofmann",
  target_hub: "",
  via_hub: "",
  sharing: state === "requested" ? "confirm" : "public",
  published_rating: null,
  opened_at: null,
  stale_at: "2026-11-30T10:00:00",
  rated_at: null,
  rating: null,
  note: null,
  rating_stars: null,
  published_rating_stars: null,
});

function draw(props: Partial<Parameters<typeof Connect>[0]> = {}) {
  render(
    <I18nProvider>
      <Connect entityId="lena-hofmann" name="Lena Hofmann" mode="ask" {...props} />
    </I18nProvider>,
  );
}

describe("connecting to a result", () => {
  beforeEach(() => localStorage.setItem("adobee-locale", "en"));
  afterEach(() => vi.restoreAllMocks());

  it("says before the click that a confirm entry will wait for its owner", () => {
    draw();
    expect(screen.getByRole("button", { name: en["connect.ask"] })).toBeInTheDocument();
    expect(screen.getByText(en["connect.askNote"].replace("{name}", "Lena Hofmann"))).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: en["connect.now"] })).not.toBeInTheDocument();
  });

  it("offers a plain Connect for a public entry, with no waiting note", () => {
    draw({ mode: "now" });
    expect(screen.getByRole("button", { name: en["connect.now"] })).toBeInTheDocument();
    expect(screen.queryByText(/waits for their yes/)).not.toBeInTheDocument();
  });

  it("draws nothing for an entry nobody may ask for", () => {
    draw({ mode: null });
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("asks once, through the hub the result came from, and then says it is waiting", async () => {
    const connect = vi.spyOn(api, "connect").mockResolvedValue(row("requested"));
    const onConnected = vi.fn();
    draw({ targetHub: "zurich", onConnected });
    fireEvent.click(screen.getByRole("button", { name: en["connect.ask"] }));

    expect(await screen.findByText(en["connect.waiting"])).toBeInTheDocument();
    expect(connect).toHaveBeenCalledWith(
      expect.objectContaining({ entity_id: "lena-hofmann", target_hub: "zurich", requester: expect.any(String) }),
    );
    expect(screen.queryByRole("button", { name: en["connect.ask"] })).not.toBeInTheDocument();
    expect(onConnected).toHaveBeenCalledTimes(1);
  });

  it("says when an open introduction can be scored until", async () => {
    vi.spyOn(api, "connect").mockResolvedValue(row("open"));
    draw({ mode: "now" });
    fireEvent.click(screen.getByRole("button", { name: en["connect.now"] }));
    expect(await screen.findByText(/Connected\. You can say how it went until .*2026/)).toBeInTheDocument();
  });

  it("shows the hub's refusal and keeps the button", async () => {
    vi.spyOn(api, "connect").mockRejectedValue(new Error("lena-hofmann is blocked on this hub"));
    draw();
    fireEvent.click(screen.getByRole("button", { name: en["connect.ask"] }));
    expect(await screen.findByText("lena-hofmann is blocked on this hub")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: en["connect.ask"] })).toBeEnabled();
  });
});
