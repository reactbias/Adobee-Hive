import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, type DirectoryHub } from "../api";
import { I18nProvider } from "../i18n";
import en from "../i18n/en";
import InstanceFinder from "./InstanceFinder";

const hub = (over: Partial<DirectoryHub> = {}): DirectoryHub => ({
  hub: "basel.example",
  url: "https://basel.example",
  home: true,
  blocked: false,
  name: "Hive Basel",
  description: "Stays, tables and services in Basel.",
  admission: "vetted",
  accepting: true,
  entities: 12,
  error: null,
  error_stars: null,
  evidence: 0,
  verdict: "unproven",
  why: "no introductions through this hub yet",
  ...over,
});

/** A peer nobody has asked: every unknown is null, exactly as the backend sends it. */
const unasked = (over: Partial<DirectoryHub> = {}): DirectoryHub =>
  hub({
    hub: "172.20.10.7:8421",
    url: "http://172.20.10.7:8421",
    home: false,
    name: "",
    description: "",
    admission: "unknown",
    accepting: null,
    entities: null,
    known: false,
    last_asked: null,
    last_asked_ok: null,
    ...over,
  });

const show = (onPick = vi.fn(), onJoin = vi.fn()) =>
  render(
    <I18nProvider>
      <InstanceFinder onPick={onPick} onJoin={onJoin} />
    </I18nProvider>,
  );

describe("the instance finder", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.setItem("adobee-locale", "en");
    sessionStorage.clear();
  });

  it("lists a hub with what it carries, whether it is accepting, and how many entities", async () => {
    vi.spyOn(api, "directory").mockResolvedValue({ hubs: [hub()] });
    show();

    expect(await screen.findByText("Hive Basel")).toBeInTheDocument();
    expect(screen.getByText("Stays, tables and services in Basel.")).toBeInTheDocument();
    expect(screen.getByText(en["finder.accepting"])).toBeInTheDocument();
    expect(screen.getByText(en["finder.admission.vetted"])).toBeInTheDocument();
    expect(screen.getByText("12 entities")).toBeInTheDocument();
  });

  // "172.20.10.7:8421 / Not accepting members{n} entities" — three separate lies in one row.
  describe("a peer nobody has asked yet", () => {
    it("never prints a placeholder with nothing to put in it", async () => {
      vi.spyOn(api, "directory").mockResolvedValue({ hubs: [unasked()] });
      const { container } = show();

      await screen.findByText(en["finder.entitiesUnknown"]);
      expect(container.textContent).not.toMatch(/\{/);
      expect(screen.queryByText(/\{n\}/)).toBeNull();
    });

    it("says the entity count is not known rather than counting to zero", async () => {
      vi.spyOn(api, "directory").mockResolvedValue({ hubs: [unasked()] });
      show();

      expect(await screen.findByText(en["finder.entitiesUnknown"])).toBeInTheDocument();
      expect(screen.queryByText("0 entities")).toBeNull();
    });

    it("does not advertise a hub that might be wide open as closed", async () => {
      vi.spyOn(api, "directory").mockResolvedValue({ hubs: [unasked()] });
      show();

      expect(await screen.findByText(en["finder.acceptingUnknown"])).toBeInTheDocument();
      expect(screen.queryByText(en["finder.closed"])).toBeNull();
      expect(screen.queryByText(en["finder.accepting"])).toBeNull();
    });

    it("says it has never been asked, which is the honest sentence while it is true", async () => {
      vi.spyOn(api, "directory").mockResolvedValue({ hubs: [unasked()] });
      show();

      expect(await screen.findByText(en["finder.asked.never"])).toBeInTheDocument();
    });
  });

  it("never renders a literal placeholder for any shape of row", async () => {
    vi.spyOn(api, "directory").mockResolvedValue({
      hubs: [
        hub(),
        unasked(),
        unasked({ hub: "stale.example", name: "Hive Stale", entities: 14, last_asked: new Date().toISOString() }),
        hub({
          hub: "blocked.example",
          name: "Hive Blocked",
          blocked: true,
          home: false,
          error: 7,
          verdict: "weak",
          evidence: 9,
        }),
      ],
    });
    const { container } = show();

    await screen.findByText("Hive Blocked");
    expect(container.textContent).not.toMatch(/[{}]/);
  });

  describe("the calibration line", () => {
    it("says the verdict and the evidence once, not twice", async () => {
      vi.spyOn(api, "directory").mockResolvedValue({ hubs: [hub({ evidence: 0 })], min_evidence: 3 });
      const { container } = show();

      await screen.findByText(en["finder.cal.line.unprovenNone"]);
      expect(container.textContent?.match(/scored introductions/g)).toHaveLength(1);
    });

    it("says how far an unproven hub is from meaning anything", async () => {
      vi.spyOn(api, "directory").mockResolvedValue({ hubs: [hub({ evidence: 2 })], min_evidence: 3 });
      show();

      expect(await screen.findByText("Unproven, 2 scored introductions and 3 needed")).toBeInTheDocument();
    });

    it("keeps the hub's own words as the detail rather than reassembling them", async () => {
      vi.spyOn(api, "directory").mockResolvedValue({ hubs: [hub({ why: "4 scored; 3 needed to mean anything" })] });
      show();

      expect(await screen.findByTitle("4 scored; 3 needed to mean anything")).toBeInTheDocument();
    });
  });

  describe("when a peer was last asked", () => {
    it("renders the moment as relative time, with the exact stamp for anyone who wants it", async () => {
      const asked = new Date(Date.now() - 120_000).toISOString();
      vi.spyOn(api, "directory").mockResolvedValue({
        hubs: [unasked({ name: "Hive Zurich", entities: 14, last_asked: asked, last_asked_ok: true })],
      });
      show();

      expect(await screen.findByText("Asked 2 minutes ago")).toBeInTheDocument();
      expect(screen.getByText("Asked 2 minutes ago")).toHaveAttribute("title", expect.stringMatching(/\d/));
    });

    it("keeps the last good answer when the latest ask went unanswered", async () => {
      const asked = new Date(Date.now() - 60_000).toISOString();
      const answered = new Date(Date.now() - 600_000).toISOString();
      vi.spyOn(api, "directory").mockResolvedValue({
        hubs: [
          unasked({
            name: "Hive Zurich",
            entities: 14,
            admission: "open",
            accepting: true,
            known: true,
            last_asked: asked,
            last_asked_ok: false,
            last_answered: answered,
            stale: true,
          }),
        ],
      });
      show();

      expect(await screen.findByText(/Asked 1 minute ago, no answer/)).toBeInTheDocument();
      expect(screen.getByText("14 entities")).toBeInTheDocument();
      expect(screen.getByText("Hive Zurich")).toBeInTheDocument();
    });

    it("says this hub answers for itself rather than timing an ask it never makes", async () => {
      vi.spyOn(api, "directory").mockResolvedValue({ hubs: [hub()] });
      show();

      expect(await screen.findByText(en["finder.asked.home"])).toBeInTheDocument();
    });
  });

  it("says a hub with a closed door is not accepting members", async () => {
    vi.spyOn(api, "directory").mockResolvedValue({ hubs: [hub({ accepting: false, admission: "closed" })] });
    show();
    expect(await screen.findByText(en["finder.closed"])).toBeInTheDocument();
  });

  it("reads a positive calibration error as over-promising, never as a score", async () => {
    vi.spyOn(api, "directory").mockResolvedValue({ hubs: [hub({ error: 7, verdict: "weak", evidence: 9 })] });
    show();
    expect(await screen.findByText(/Over-promised by 0.7 stars/)).toBeInTheDocument();
  });

  it("reads a negative calibration error as the hub underselling what it offered", async () => {
    vi.spyOn(api, "directory").mockResolvedValue({ hubs: [hub({ error: -12, verdict: "good", evidence: 9 })] });
    show();
    expect(await screen.findByText(/Undersold itself by 1.2 stars/)).toBeInTheDocument();
  });

  it("says thin evidence is unproven rather than showing it as zero", async () => {
    vi.spyOn(api, "directory").mockResolvedValue({
      hubs: [hub({ error: 9, verdict: "unproven", evidence: 1 })],
      min_evidence: 3,
    });
    show();
    expect(await screen.findByText("Unproven, 1 scored introductions and 3 needed")).toBeInTheDocument();
    expect(screen.queryByText("0.9")).toBeNull();
  });

  it("spells out which way calibration reads", async () => {
    vi.spyOn(api, "directory").mockResolvedValue({ hubs: [hub()] });
    show();
    expect(await screen.findByText(en["finder.cal.explain"])).toBeInTheDocument();
  });

  it("is no longer labelled a first pass", async () => {
    vi.spyOn(api, "directory").mockResolvedValue({ hubs: [hub()] });
    show();
    await screen.findAllByRole("listitem");
    expect(screen.queryByText(/First pass/)).toBeNull();
  });

  it("falls back to this hub, and says so, when the directory is not deployed", async () => {
    vi.spyOn(api, "directory").mockRejectedValue(new ApiError("Not Found", 404));
    show();

    expect(await screen.findByText(en["finder.notDeployed"])).toBeInTheDocument();
    expect(screen.getByText(en["finder.thisHub"])).toBeInTheDocument();
    expect(screen.getByRole("button", { name: en["finder.use"] })).toBeEnabled();
  });

  it("falls back the same way when the backend cannot be reached at all", async () => {
    vi.spyOn(api, "directory").mockRejectedValue(new Error("error.offline"));
    show();
    expect(await screen.findByText(en["finder.thisHub"])).toBeInTheDocument();
  });

  it("remembers the pick for this tab and hands over to the app", async () => {
    vi.spyOn(api, "directory").mockResolvedValue({ hubs: [hub()] });
    const onPick = vi.fn();
    show(onPick);

    await userEvent.click(await screen.findByRole("button", { name: en["finder.use"] }));
    await waitFor(() => expect(onPick).toHaveBeenCalledWith("basel.example"));
    expect(sessionStorage.getItem("adobee-hub")).toBe("basel.example");
    expect(localStorage.getItem("adobee-hub")).toBeNull();
  });

  it("is honest that picking another hub does not yet move the app to it", async () => {
    vi.spyOn(api, "directory").mockResolvedValue({ hubs: [hub(), hub({ hub: "zurich.example", home: false })] });
    show();

    const rows = await screen.findAllByRole("listitem");
    expect(within(rows[0]).queryByText(en["finder.peerNotWired"])).toBeNull();
    expect(within(rows[1]).getByText(en["finder.peerNotWired"])).toBeInTheDocument();
  });

  it("offers no way to use or join a hub this one has blocked", async () => {
    vi.spyOn(api, "directory").mockResolvedValue({ hubs: [hub({ blocked: true, apply_at: "/api/hub/register" })] });
    show();
    expect(await screen.findByRole("button", { name: en["finder.use"] })).toBeDisabled();
    expect(screen.getByRole("button", { name: en["finder.join"] })).toBeDisabled();
    expect(screen.getByText(en["finder.blocked"])).toBeInTheDocument();
  });
});

// What a person is deciding between, not the field list: what it carries, will it have me, can I trust it.
describe("choosing between hives", () => {
  const rows = () => screen.findAllByRole("listitem");
  const names = async () => (await rows()).map((r) => within(r).getByRole("heading").textContent);

  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.setItem("adobee-locale", "en");
    sessionStorage.clear();
  });

  it("groups each hive under the three questions", async () => {
    vi.spyOn(api, "directory").mockResolvedValue({ hubs: [hub()] });
    show();

    const [row] = await rows();
    for (const q of ["finder.q.carries", "finder.q.admits", "finder.q.trust"] as const)
      expect(within(row).getByText(en[q])).toBeInTheDocument();
  });

  it("says a hive's admission rules are unknown when nobody has asked it", async () => {
    vi.spyOn(api, "directory").mockResolvedValue({ hubs: [unasked()] });
    show();
    expect(await screen.findByText(en["finder.admission.unknown"])).toBeInTheDocument();
  });

  it("offers no application to a closed door, and says why", async () => {
    vi.spyOn(api, "directory").mockResolvedValue({
      hubs: [hub({ accepting: false, admission: "closed", apply_at: "/api/hub/register" })],
    });
    show();
    expect(await screen.findByRole("button", { name: en["finder.join"] })).toBeDisabled();
    expect(screen.getByText(en["finder.joinClosed"])).toBeInTheDocument();
  });

  it("hands a hive to the application when Join is pressed", async () => {
    vi.spyOn(api, "directory").mockResolvedValue({ hubs: [hub({ apply_at: "/api/hub/register" })] });
    const onJoin = vi.fn();
    show(vi.fn(), onJoin);

    await userEvent.click(await screen.findByRole("button", { name: en["finder.join"] }));
    expect(onJoin).toHaveBeenCalledWith(expect.objectContaining({ hub: "basel.example" }));
  });

  it("marks the hive you are on without putting it first", async () => {
    vi.spyOn(api, "directory").mockResolvedValue({
      hubs: [hub({ name: "Zeta" }), unasked({ hub: "alpha.example", name: "Alpha" })],
    });
    show();

    expect(await names()).toEqual(["Alpha", "Zeta"]);
    const [alpha, zeta] = await rows();
    expect(within(zeta).getByText(en["finder.home"])).toBeInTheDocument();
    expect(within(alpha).queryByText(en["finder.home"])).toBeNull();
  });

  it("searches across name, address and what a hive carries", async () => {
    vi.spyOn(api, "directory").mockResolvedValue({
      hubs: [hub(), unasked({ name: "Hive Zürich", description: "Cafés" })],
    });
    show();
    await rows();

    await userEvent.type(screen.getByRole("searchbox", { name: en["finder.search"] }), "cafés");
    expect(await names()).toEqual(["Hive Zürich"]);

    await userEvent.clear(screen.getByRole("searchbox"));
    await userEvent.type(screen.getByRole("searchbox"), "nothing like it");
    expect(await screen.findByText(en["finder.noMatch"])).toBeInTheDocument();
  });

  it("filters to hives that will take you, and to hives with a track record", async () => {
    vi.spyOn(api, "directory").mockResolvedValue({
      hubs: [
        hub({ name: "Open", hub: "a", error: 2, verdict: "good", evidence: 9 }),
        hub({ name: "Closed", hub: "b", accepting: false, admission: "closed" }),
        unasked({ name: "Unknown", hub: "c" }),
      ],
    });
    show();
    await rows();

    const taking = screen.getByRole("button", { name: en["finder.filter.accepting"] });
    await userEvent.click(taking);
    expect(await names()).toEqual(["Open"]);
    expect(taking).toHaveAttribute("aria-pressed", "true");

    await userEvent.click(taking);
    await userEvent.click(screen.getByRole("button", { name: en["finder.filter.proven"] }));
    expect(await names()).toEqual(["Open"]);
  });
});
