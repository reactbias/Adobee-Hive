import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, type AdminNeighbours, type AdminOverview } from "../api";
import { I18nProvider } from "../i18n";
import en from "../i18n/en";
import NetworkPanel from "./NetworkPanel";

// The live hub as it answers today: 22 entities, no peers, nothing blocked. That is the common case, and one
// honestly labelled node has to look deliberate rather than broken.
const LIVE: AdminOverview = {
  hub: "local",
  name: "Adobee Hive (Basel)",
  index: { entities: 22 },
  neighbours: { configured: 0, blocked: 0, with_evidence: 0 },
  blocklist: { hubs: 0, entities: 0 },
  connections: { awaiting_confirmation: 1, awaiting_rating: 2, rated: 5, stale: 0, declined: 0 },
  peers: [],
};

const PEERS: AdminNeighbours = {
  peers: [
    {
      hub: "zurich",
      url: "https://zurich.example",
      blocked: false,
      error: -4,
      error_stars: -0.4,
      evidence: 6,
      verdict: "good",
      why: "modest about its own ratings",
    },
    {
      hub: "spam.example",
      url: "https://spam.example",
      blocked: true,
      error: null,
      error_stars: null,
      evidence: 0,
      verdict: "unproven",
      why: "relayed forged cards",
    },
  ],
  blocked_hubs: ["spam.example"],
};

const show = () =>
  render(
    <I18nProvider>
      <NetworkPanel />
    </I18nProvider>,
  );

/** The hub rows, not the four counts above them: both are lists. */
const hubRows = async () =>
  within(await screen.findByRole("list", { name: en["network.hubs"] })).getAllByRole("listitem");

describe("the live node view", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.setItem("adobee-locale", "en");
    vi.spyOn(api, "adminOverview").mockResolvedValue(LIVE);
    vi.spyOn(api, "adminNeighbours").mockResolvedValue({ peers: [], blocked_hubs: [] });
    // Not on `main` yet, which is how the deployed hub actually answers.
    vi.spyOn(api, "directory").mockRejectedValue(new ApiError("Not Found", 404));
  });

  it("counts what the hub carries and what is open, from the live overview", async () => {
    show();
    expect(await screen.findByText(en["network.count.entities"])).toBeInTheDocument();
    expect(screen.getByText(en["network.count.entities"]).parentElement).toHaveTextContent("22");
    expect(screen.getByText(en["network.count.live"]).parentElement).toHaveTextContent("3");
  });

  it("draws one node, and says why it is alone, when no peers are configured", async () => {
    show();
    expect(await screen.findByText(en["network.alone"])).toBeInTheDocument();
    expect(screen.getByText(en["network.count.peers"]).parentElement).toHaveTextContent("0");
    expect(screen.getByRole("img", { name: en["network.diagram"] })).toBeInTheDocument();
    expect(await hubRows()).toHaveLength(1);
  });

  it("names this hub in the middle rather than leaving the centre unlabelled", async () => {
    show();
    expect(await screen.findAllByText("Adobee Hive (Basel)")).not.toHaveLength(0);
    expect(screen.getByText(en["network.thisHub"])).toBeInTheDocument();
  });

  it("needs no login: it reads only the open endpoints", async () => {
    const login = vi.spyOn(api, "adminLogin");
    show();
    await screen.findByText(en["network.alone"]);
    expect(login).not.toHaveBeenCalled();
  });

  it("gives every configured peer a node and a row", async () => {
    vi.spyOn(api, "adminNeighbours").mockResolvedValue(PEERS);
    show();
    expect(await hubRows()).toHaveLength(3);
    expect(screen.queryByText(en["network.alone"])).toBeNull();
    expect(screen.getByText(en["network.count.peers"]).parentElement).toHaveTextContent("2");
  });

  it("still shows a blocked peer, and says nothing passes", async () => {
    vi.spyOn(api, "adminNeighbours").mockResolvedValue(PEERS);
    show();
    expect(await screen.findByText(en["network.blockedHub"])).toBeInTheDocument();
    // Still drawn, not dropped: a cut cell in the honeycomb as well as its row underneath.
    const row = (await hubRows()).find((r) => r.textContent?.includes("spam.example"));
    expect(row).toBeDefined();
    expect(document.querySelector(".net-cell.blocked")).not.toBeNull();
    expect(document.querySelector(".net-edge.cut .net-cut")).not.toBeNull();
  });

  it("reads a negative calibration as the hub underselling what it offered, never as a bad score", async () => {
    vi.spyOn(api, "adminNeighbours").mockResolvedValue(PEERS);
    show();
    expect(await screen.findByText("Undersold itself by 0.4 stars")).toBeInTheDocument();
  });

  it("calls a peer we have not asked unknown, not zero", async () => {
    vi.spyOn(api, "adminNeighbours").mockResolvedValue(PEERS);
    show();
    const zurich = (await hubRows()).find((r) => r.textContent?.includes("zurich"))!;
    expect(within(zurich).getByText(/entity count unknown/)).toBeInTheDocument();
    expect(within(zurich).getByText(/admission unknown/)).toBeInTheDocument();
  });

  it("survives a peer list that does not answer, and still draws this hub", async () => {
    vi.spyOn(api, "adminNeighbours").mockRejectedValue(new Error("error.offline"));
    show();
    expect(await screen.findByText(en["network.alone"])).toBeInTheDocument();
  });

  it("says the numbers are not live when the hub itself is unreachable", async () => {
    vi.spyOn(api, "adminOverview").mockRejectedValue(new Error("error.offline"));
    show();
    expect(await screen.findByText(en["network.unreachable"])).toBeInTheDocument();
  });

  it("spells out which way the calibration on an edge reads", async () => {
    show();
    expect(await screen.findByText(en["network.legend"])).toBeInTheDocument();
  });
});
