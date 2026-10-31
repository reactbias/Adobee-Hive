import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, type AdminOverview, type AdminPeer, type AdminSettings, type Application } from "../api";
import { I18nProvider } from "../i18n";
import en from "../i18n/en";
import AdminPanel from "./AdminPanel";

const OVERVIEW: AdminOverview = {
  hub: "local",
  name: "Adobee Hive (Basel)",
  index: { entities: 7 },
  neighbours: { configured: 2, blocked: 1, with_evidence: 1 },
  blocklist: { hubs: 1, entities: 2 },
  connections: { awaiting_confirmation: 0, awaiting_rating: 1, rated: 3, stale: 0, declined: 0 },
  peers: [],
};

const SETTINGS: AdminSettings = {
  fields: [
    {
      key: "name",
      label: "Name",
      value: "Adobee Hive (Basel)",
      help: "Shown to a person reading a result.",
      editable: true,
    },
    {
      key: "verification",
      label: "Verification",
      value: "signed",
      help: "What this hub checks before carrying an entity.",
      options: ["none", "email", "signed", "identity"],
      editable: true,
    },
  ],
  calibration: { lower_is_better: true, help: "published minus realised", min_evidence: 3, half_life_days: 90 },
};

const APPLICATION: Application = {
  id: "app_1",
  created_at: "2026-10-31T09:00:00",
  state: "pending",
  entity_id: "cafe-neu",
  kind: "stay",
  name: "Cafe Neu",
  custody: "hub",
  verification: "signed",
  proofs: [],
  checks: [
    { check: "shape", ok: true, detail: "" },
    { check: "signature", ok: true, detail: "" },
  ],
  decided_at: null,
  decided_by: null,
  reason: "every application here is read by a person",
  next: "Nothing: a person reads every application.",
};

const PEER: AdminPeer = {
  url: "https://a.example",
  hub: "a.example",
  hub_id: "a.example",
  name: "",
  note: "",
  state: "active",
  added_at: "2026-10-30T09:00:00",
  added_by: "session",
  changed_at: null,
  removed_at: null,
  removed_reason: null,
  known: false,
  description: "",
  verification: "unknown",
  admission: "unknown",
  entities: null,
  last_asked: null,
  last_asked_ok: null,
  last_answered: null,
  stale: false,
  blocked: false,
  error: null,
  error_stars: null,
  evidence: 8,
  verdict: "unproven",
  why: "over its own claim",
};

const show = () =>
  render(
    <I18nProvider>
      <AdminPanel />
    </I18nProvider>,
  );

/** Sign in with the stubbed password, then wait for the dashboard. */
async function signIn() {
  show();
  await userEvent.type(screen.getByLabelText(en["admin.password"]), "hunter2");
  await userEvent.click(screen.getByRole("button", { name: en["admin.signIn"] }));
  return screen.findByRole("tab", { name: en["admin.view.overview"] });
}

describe("the admin panel", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.setItem("adobee-locale", "en");
    sessionStorage.clear();
    vi.spyOn(api, "adminOverview").mockResolvedValue(OVERVIEW);
    vi.spyOn(api, "adminSettings").mockResolvedValue(SETTINGS);
    vi.spyOn(api, "adminNeighbours").mockResolvedValue({ peers: [], blocked_hubs: [] });
    vi.spyOn(api, "adminPeers").mockResolvedValue({
      peers: [],
      live: [],
      seed: [],
      from_environment: false,
      blocked_hubs: [],
    });
    vi.spyOn(api, "adminBlocklist").mockResolvedValue({ entries: [], kinds: ["hub", "entity"] });
    vi.spyOn(api, "adminApplications").mockResolvedValue({
      applications: [APPLICATION],
      policy: { policy: "vetted", means: "a person reads every application" },
    });
  });

  it("asks for the password first and shows nothing else", () => {
    show();
    expect(screen.getByLabelText(en["admin.password"])).toHaveAttribute("type", "password");
    expect(screen.queryByRole("tab", { name: en["admin.view.blocklist"] })).toBeNull();
  });

  it("says so when the password is wrong, and hands out nothing", async () => {
    vi.spyOn(api, "adminLogin").mockRejectedValue(new ApiError("Wrong password.", 403));
    show();
    await userEvent.type(screen.getByLabelText(en["admin.password"]), "guess");
    await userEvent.click(screen.getByRole("button", { name: en["admin.signIn"] }));

    expect(await screen.findByText(en["admin.wrongPassword"])).toBeInTheDocument();
    expect(sessionStorage.getItem("adobee-admin-session")).toBeNull();
  });

  it("says when to try again after a lockout", async () => {
    vi.spyOn(api, "adminLogin").mockRejectedValue(new ApiError("Too many sign-in attempts.", 429, "754"));
    show();
    await userEvent.type(screen.getByLabelText(en["admin.password"]), "guess");
    await userEvent.click(screen.getByRole("button", { name: en["admin.signIn"] }));

    expect(await screen.findByText(en["admin.lockedOut"].replace("{s}", "754"))).toBeInTheDocument();
  });

  it("says administration is switched off when the hub has no password", async () => {
    vi.spyOn(api, "adminLogin").mockRejectedValue(new ApiError("no ADMIN_PASSWORD", 503));
    show();
    await userEvent.type(screen.getByLabelText(en["admin.password"]), "anything");
    await userEvent.click(screen.getByRole("button", { name: en["admin.signIn"] }));

    expect(await screen.findByText(en["admin.disabled"])).toBeInTheDocument();
  });

  it("keeps the session in this tab only, never in localStorage", async () => {
    vi.spyOn(api, "adminLogin").mockResolvedValue({ token: "v1.1.abc", expires_in: 1800 });
    await signIn();
    expect(sessionStorage.getItem("adobee-admin-session")).toBe("v1.1.abc");
    expect(localStorage.getItem("adobee-admin-session")).toBeNull();
  });

  it("counts the three stores on the overview", async () => {
    vi.spyOn(api, "adminLogin").mockResolvedValue({ token: "v1.1.abc", expires_in: 1800 });
    await signIn();

    for (const [label, n] of [
      [en["admin.count.entities"], "7"],
      [en["admin.count.peers"], "2"],
      [en["admin.count.blocked"], "3"],
    ]) {
      expect(screen.getByText(label).parentElement).toHaveTextContent(n);
    }
  });

  it("generates the settings form from the fields the API hands over", async () => {
    vi.spyOn(api, "adminLogin").mockResolvedValue({ token: "v1.1.abc", expires_in: 1800 });
    await signIn();

    expect(await screen.findByLabelText("Name")).toHaveValue("Adobee Hive (Basel)");
    expect(screen.getByText("Shown to a person reading a result.")).toBeInTheDocument();
    const closed = screen.getByLabelText("Verification");
    expect(closed.tagName).toBe("SELECT");
    expect(Array.from(closed.querySelectorAll("option")).map((o) => o.textContent)).toEqual([
      "none",
      "email",
      "signed",
      "identity",
    ]);
  });

  it("will not refuse an application without a reason", async () => {
    vi.spyOn(api, "adminLogin").mockResolvedValue({ token: "v1.1.abc", expires_in: 1800 });
    const decide = vi.spyOn(api, "adminDecide").mockResolvedValue(APPLICATION);
    await signIn();
    await userEvent.click(screen.getByRole("tab", { name: en["admin.view.applications"] }));

    expect(await screen.findByText("Cafe Neu")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: en["admin.applications.refuse"] })).toBeDisabled();
    expect(screen.getByText(en["admin.applications.reasonNeeded"])).toBeInTheDocument();

    await userEvent.type(screen.getByLabelText(en["admin.applications.reason"]), "no proof of the address");
    await userEvent.click(screen.getByRole("button", { name: en["admin.applications.refuse"] }));
    expect(decide).toHaveBeenCalledWith("app_1", false, "no proof of the address");
  });

  it("admits without asking for a reason", async () => {
    vi.spyOn(api, "adminLogin").mockResolvedValue({ token: "v1.1.abc", expires_in: 1800 });
    const decide = vi.spyOn(api, "adminDecide").mockResolvedValue(APPLICATION);
    await signIn();
    await userEvent.click(screen.getByRole("tab", { name: en["admin.view.applications"] }));
    await userEvent.click(await screen.findByRole("button", { name: en["admin.applications.admit"] }));

    expect(decide).toHaveBeenCalledWith("app_1", true, "");
  });

  it("says the signup queue is not deployed rather than showing an error", async () => {
    vi.spyOn(api, "adminLogin").mockResolvedValue({ token: "v1.1.abc", expires_in: 1800 });
    vi.spyOn(api, "adminApplications").mockRejectedValue(new ApiError("Not Found", 404));
    await signIn();
    await userEvent.click(screen.getByRole("tab", { name: en["admin.view.applications"] }));

    expect(await screen.findByText(en["admin.applications.notDeployed"])).toBeInTheDocument();
  });

  it("will not add a block without a reason", async () => {
    vi.spyOn(api, "adminLogin").mockResolvedValue({ token: "v1.1.abc", expires_in: 1800 });
    await signIn();
    await userEvent.click(screen.getByRole("tab", { name: en["admin.view.blocklist"] }));

    await userEvent.type(await screen.findByLabelText(en["admin.block.subject"]), "spam.example");
    expect(screen.getByRole("button", { name: en["admin.block.add"] })).toBeDisabled();
    await userEvent.type(screen.getByLabelText(en["admin.block.reason"]), "relayed forged cards");
    expect(screen.getByRole("button", { name: en["admin.block.add"] })).toBeEnabled();
  });

  it("goes back to the password form when the session is no longer accepted", async () => {
    vi.spyOn(api, "adminLogin").mockResolvedValue({ token: "v1.1.abc", expires_in: 1800 });
    vi.spyOn(api, "adminBlock").mockRejectedValue(new ApiError("Missing, wrong or expired X-Admin-Token.", 403));
    await signIn();
    await userEvent.click(screen.getByRole("tab", { name: en["admin.view.blocklist"] }));
    await userEvent.type(await screen.findByLabelText(en["admin.block.subject"]), "spam.example");
    await userEvent.type(screen.getByLabelText(en["admin.block.reason"]), "forgery");
    await userEvent.click(screen.getByRole("button", { name: en["admin.block.add"] }));

    await waitFor(() => expect(screen.getByLabelText(en["admin.password"])).toBeInTheDocument());
    expect(sessionStorage.getItem("adobee-admin-session")).toBeNull();
  });

  it("labels a peer's calibration, lower being better", async () => {
    // The Neighbours tab is PeersPanel now, so the same promise is checked through the panel that owns it.
    vi.spyOn(api, "adminLogin").mockResolvedValue({ token: "v1.1.abc", expires_in: 1800 });
    vi.spyOn(api, "adminPeers").mockResolvedValue({
      peers: [
        { ...PEER, url: "https://a.example", hub: "a.example", error: 5, error_stars: 0.5, verdict: "weak" },
        {
          ...PEER,
          url: "https://b.example",
          hub: "b.example",
          error: -5,
          error_stars: -0.5,
          verdict: "good",
        },
      ],
      live: ["https://a.example", "https://b.example"],
      seed: [],
      from_environment: false,
      blocked_hubs: [],
    });
    await signIn();
    await userEvent.click(screen.getByRole("tab", { name: en["admin.view.neighbours"] }));

    expect(await screen.findByText("Over-promised by 0.5 stars")).toBeInTheDocument();
    expect(screen.getByText("Undersold itself by 0.5 stars")).toBeInTheDocument();
  });

  it("signs out, and forgets the session token", async () => {
    vi.spyOn(api, "adminLogin").mockResolvedValue({ token: "v1.1.abc", expires_in: 1800 });
    const out = vi.spyOn(api, "adminLogout").mockResolvedValue({ signed_out: true });
    await signIn();
    await userEvent.click(screen.getByRole("button", { name: en["admin.signOut"] }));

    expect(out).toHaveBeenCalled();
    expect(screen.getByLabelText(en["admin.password"])).toBeInTheDocument();
    expect(sessionStorage.getItem("adobee-admin-session")).toBeNull();
  });
});
