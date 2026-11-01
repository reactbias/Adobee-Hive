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

  it("sends the signed card, so an introduction to somebody on a peer is not refused", async () => {
    // #172: the hub cannot take the asker's word for who a remote entity is. Without the card it has
    // nothing to check against the key that entity's own hub pinned, and answers 400 — which is what
    // every Connect on a Zürich or Bern result used to do.
    const connect = vi.spyOn(api, "connect").mockResolvedValue(row("open"));
    const signed = {
      id: "lena-hofmann",
      name: "Lena Hofmann",
      signature: "ed25519:abc",
      published_at: "2026-10-30T09:00:00",
    } as never;
    draw({ mode: "now", targetHub: "zurich", card: signed });
    fireEvent.click(screen.getByRole("button", { name: en["connect.now"] }));

    await screen.findByText(/Connected\./);
    const sent = connect.mock.calls[0][0];
    expect(sent.target_hub).toBe("zurich");
    // Byte for byte what the search returned: the signature covers the exact JSON.
    expect(sent.card).toBe(signed);
  });

  it("sends no card when the search did not hand one over, so a local introduction is unchanged", async () => {
    const connect = vi.spyOn(api, "connect").mockResolvedValue(row("open"));
    draw({ mode: "now" });
    fireEvent.click(screen.getByRole("button", { name: en["connect.now"] }));

    await screen.findByText(/Connected\./);
    expect("card" in connect.mock.calls[0][0]).toBe(false);
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
  // #171: the introduction already carried the manifest and the bearer for it, and Connect kept only `state`.
  it("browses the folder the introduction handed over, with the secret it came with", async () => {
    vi.spyOn(api, "connect").mockResolvedValue({
      ...row("open"),
      folder_link: "fl-1",
      folder: {
        owner: "lena-hofmann",
        viewer: "traveller-ab12",
        linked: true,
        files: [
          {
            path: "cv.pdf",
            bytes: 182_000,
            media_type: "application/pdf",
            digest: "sha256:abc123def456",
            visibility: "public",
            ref: "lena-hofmann/cv.pdf",
            readable: true,
          },
        ],
        withheld: 1,
      },
      folder_key: {
        id: "fk-1",
        link: "fl-1",
        handle: "traveller-ab12",
        peer: "lena-hofmann",
        secret: "s3cret",
        scheme: "Bearer",
      },
    });
    const file = vi.spyOn(api, "folderFile").mockResolvedValue(new Blob(["x"]));
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    draw({ mode: "now" });
    fireEvent.click(screen.getByRole("button", { name: en["connect.now"] }));

    expect(await screen.findByText("cv.pdf")).toBeInTheDocument();
    expect(screen.getByText(en["folder.title"].replace("{name}", "Lena Hofmann"))).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: en["folder.take"] }));
    await vi.waitFor(() => expect(file).toHaveBeenCalledWith("s3cret", "cv.pdf"));
  });

  // A remote introduction comes back without a folder: hub.connect fills it on the local branch only.
  it("draws no folder when the introduction did not carry one", async () => {
    vi.spyOn(api, "connect").mockResolvedValue(row("open"));
    draw({ mode: "now" });
    fireEvent.click(screen.getByRole("button", { name: en["connect.now"] }));
    expect(await screen.findByText(/You can say how it went/)).toBeInTheDocument();
    expect(screen.queryByText(en["folder.eyebrow"])).not.toBeInTheDocument();
  });
});
