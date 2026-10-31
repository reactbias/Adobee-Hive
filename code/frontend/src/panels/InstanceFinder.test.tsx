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

const show = (onPick = vi.fn()) =>
  render(
    <I18nProvider>
      <InstanceFinder onPick={onPick} />
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

  it("says a hub with a closed door is not accepting members", async () => {
    vi.spyOn(api, "directory").mockResolvedValue({ hubs: [hub({ accepting: false, admission: "closed" })] });
    show();
    expect(await screen.findByText(en["finder.closed"])).toBeInTheDocument();
  });

  it("reads a positive calibration error as over-promising, never as a score", async () => {
    vi.spyOn(api, "directory").mockResolvedValue({ hubs: [hub({ error: 7, verdict: "weak", evidence: 9 })] });
    show();
    expect(await screen.findByText("Over-promised by 0.7 stars")).toBeInTheDocument();
  });

  it("reads a negative calibration error as the hub underselling what it offered", async () => {
    vi.spyOn(api, "directory").mockResolvedValue({ hubs: [hub({ error: -12, verdict: "good", evidence: 9 })] });
    show();
    expect(await screen.findByText("Undersold itself by 1.2 stars")).toBeInTheDocument();
  });

  it("says thin evidence is unproven rather than showing it as zero", async () => {
    vi.spyOn(api, "directory").mockResolvedValue({ hubs: [hub({ error: 9, verdict: "unproven", evidence: 1 })] });
    show();
    expect(await screen.findByText(en["finder.cal.unproven"])).toBeInTheDocument();
  });

  it("spells out which way calibration reads", async () => {
    vi.spyOn(api, "directory").mockResolvedValue({ hubs: [hub()] });
    show();
    expect(await screen.findByText(en["finder.cal.explain"])).toBeInTheDocument();
  });

  it("says on screen that it is a first pass, not a finished design", async () => {
    vi.spyOn(api, "directory").mockResolvedValue({ hubs: [hub()] });
    show();
    expect(await screen.findByText(en["finder.draft"])).toBeInTheDocument();
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

  it("offers no way to use a hub this one has blocked", async () => {
    vi.spyOn(api, "directory").mockResolvedValue({ hubs: [hub({ blocked: true })] });
    show();
    expect(await screen.findByRole("button", { name: en["finder.use"] })).toBeDisabled();
  });
});
