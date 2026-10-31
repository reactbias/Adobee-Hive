import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, type AdminPeer } from "../api";
import { I18nProvider } from "../i18n";
import en from "../i18n/en";
import PeersPanel from "./PeersPanel";

const ZURICH: AdminPeer = {
  url: "https://hive-zurich.example",
  hub: "hive-zurich.example",
  hub_id: "hive-zurich.example",
  name: "Adobee Hive (Zurich)",
  note: "",
  state: "active",
  added_at: "2026-10-30T09:00:00",
  added_by: "session",
  changed_at: null,
  removed_at: null,
  removed_reason: null,
  answers: true,
  last_checked_at: "2026-10-31T08:00:00",
  last_error: "",
  blocked: false,
  error: -10,
  error_stars: -1,
  evidence: 4,
  verdict: "modest",
  why: "under-promised by one star",
};

const SILENT: AdminPeer = {
  ...ZURICH,
  url: "https://hive-bern.example",
  hub: "hive-bern.example",
  hub_id: "hive-bern.example",
  name: "Adobee Hive (Bern)",
  answers: false,
  last_error: "ConnectError: no answer",
  error: null,
  error_stars: null,
  evidence: 0,
  verdict: "unproven",
  why: "no introductions through this hub yet",
};

const UNASKED: AdminPeer = {
  ...SILENT,
  url: "https://hive-genf.example",
  hub: "hive-genf.example",
  answers: null,
  last_checked_at: null,
};

const show = () =>
  render(
    <I18nProvider>
      <PeersPanel />
    </I18nProvider>,
  );

const peers = (rows: AdminPeer[], from_environment = false) => ({
  peers: rows,
  live: rows.filter((p) => p.state === "active").map((p) => p.url),
  seed: [],
  from_environment,
  blocked_hubs: [],
});

describe("the connected hubs", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.setItem("adobee-locale", "en");
  });

  it("lists each peer with its URL, its id, whether it answers and its calibration", async () => {
    vi.spyOn(api, "adminPeers").mockResolvedValue(peers([ZURICH, SILENT, UNASKED]));
    show();

    expect(await screen.findByText("Adobee Hive (Zurich)")).toBeInTheDocument();
    expect(screen.getByText("https://hive-zurich.example")).toBeInTheDocument();
    expect(screen.getByText(en["admin.peers.answers"])).toBeInTheDocument();
    expect(screen.getByText(en["admin.peers.silent"])).toBeInTheDocument();
    expect(screen.getByText(en["admin.peers.unasked"])).toBeInTheDocument();
    expect(screen.getByText("ConnectError: no answer")).toBeInTheDocument();
  });

  it("says when the hub is still running on its environment setting", async () => {
    vi.spyOn(api, "adminPeers").mockResolvedValue(peers([], true));
    show();

    expect(await screen.findByText(en["admin.peers.fromEnv"])).toBeInTheDocument();
    expect(screen.getByText(en["admin.peers.empty"])).toBeInTheDocument();
  });

  it("adds a peer only with a URL and a reason", async () => {
    vi.spyOn(api, "adminPeers").mockResolvedValue(peers([]));
    const add = vi.spyOn(api, "adminAddPeer").mockResolvedValue(ZURICH);
    show();

    await screen.findByText(en["admin.peers.add"]);
    expect(screen.getByRole("button", { name: en["admin.peers.addDo"] })).toBeDisabled();

    await userEvent.type(screen.getByLabelText(en["admin.peers.url"]), "https://hive-zurich.example");
    expect(screen.getByRole("button", { name: en["admin.peers.addDo"] })).toBeDisabled();
    await userEvent.type(screen.getByLabelText(en["admin.peers.reason"]), "regional partner");
    await userEvent.click(screen.getByRole("button", { name: en["admin.peers.addDo"] }));

    expect(add).toHaveBeenCalledWith("https://hive-zurich.example", "regional partner", "");
  });

  it("says what removing a peer will do, and names it, before it does it", async () => {
    vi.spyOn(api, "adminPeers").mockResolvedValue(peers([ZURICH]));
    const remove = vi.spyOn(api, "adminRemovePeer").mockResolvedValue(ZURICH);
    show();

    await userEvent.click(await screen.findByRole("button", { name: en["admin.peers.removeButton"] }));

    expect(
      screen.getByText(en["admin.peers.removeConfirm"].replace("{name}", "Adobee Hive (Zurich)")),
    ).toBeInTheDocument();
    expect(screen.getByText(en["admin.peers.removeWill"])).toBeInTheDocument();
    expect(screen.getByText(en["admin.peers.removeNotBlock"])).toBeInTheDocument();
    expect(remove).not.toHaveBeenCalled();

    await userEvent.type(screen.getByLabelText(en["admin.peers.reason"]), "they stopped answering");
    await userEvent.click(screen.getByRole("button", { name: en["admin.peers.removeDo"] }));
    expect(remove).toHaveBeenCalledWith("https://hive-zurich.example", "they stopped answering");
  });

  it("offers blocking as the stronger, different act", async () => {
    vi.spyOn(api, "adminPeers").mockResolvedValue(peers([ZURICH]));
    const block = vi.spyOn(api, "adminBlock").mockResolvedValue({
      kind: "hub",
      subject: "hive-zurich.example",
      reason: "forged a card",
      added_at: "2026-10-31T10:00:00",
      added_by: "admin",
    });
    show();

    await userEvent.click(await screen.findByRole("button", { name: en["admin.peers.blockButton"] }));
    expect(screen.getByText(en["admin.peers.blockWill"])).toBeInTheDocument();
    expect(screen.getByText(en["admin.peers.blockNotRemove"])).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText(en["admin.peers.reason"]), "forged a card");
    await userEvent.click(screen.getByRole("button", { name: en["admin.peers.blockDo"] }));
    expect(block).toHaveBeenCalledWith("hub", "hive-zurich.example", "forged a card");
  });

  it("edits a peer's name and id, with a reason", async () => {
    vi.spyOn(api, "adminPeers").mockResolvedValue(peers([ZURICH]));
    const edit = vi.spyOn(api, "adminEditPeer").mockResolvedValue(ZURICH);
    show();

    await userEvent.click(await screen.findByRole("button", { name: en["admin.peers.edit"] }));
    await userEvent.clear(screen.getByLabelText(en["admin.peers.name"]));
    await userEvent.type(screen.getByLabelText(en["admin.peers.name"]), "Hive Zürich");
    await userEvent.type(screen.getByLabelText(en["admin.peers.reason"]), "they renamed themselves");
    await userEvent.click(screen.getByRole("button", { name: en["admin.peers.save"] }));

    expect(edit).toHaveBeenCalledWith(
      "https://hive-zurich.example",
      "they renamed themselves",
      "Hive Zürich",
      "hive-zurich.example",
    );
  });

  it("asks every hub whether it answers, on demand and not on every page load", async () => {
    const list = vi.spyOn(api, "adminPeers").mockResolvedValue(peers([ZURICH]));
    const check = vi.spyOn(api, "adminCheckPeers").mockResolvedValue({ peers: [ZURICH] });
    show();

    await screen.findByText("Adobee Hive (Zurich)");
    expect(check).not.toHaveBeenCalled();
    expect(list).toHaveBeenCalledTimes(1);

    await userEvent.click(screen.getByRole("button", { name: en["admin.peers.check"] }));
    expect(check).toHaveBeenCalled();
  });

  it("shows a removed peer as removed, with nothing left to act on", async () => {
    vi.spyOn(api, "adminPeers").mockResolvedValue(
      peers([{ ...ZURICH, state: "removed", removed_reason: "they sell placement" }]),
    );
    show();

    expect(await screen.findByText(en["admin.peers.removed"])).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: en["admin.peers.removeButton"] })).not.toBeInTheDocument();
  });
});
