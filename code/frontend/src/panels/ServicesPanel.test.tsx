import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, type AdminService } from "../api";
import { I18nProvider } from "../i18n";
import en from "../i18n/en";
import ServicesPanel from "./ServicesPanel";

const WARNING = "A key is stored on this hub, in its database, in the clear.";

const OFF: AdminService = {
  name: "openai",
  label: "OpenAI",
  purpose: "Runs the booking agent and the scout.",
  without: "The scripted planner answers.",
  env: "OPENAI_API_KEY",
  configured: false,
  source: "none",
  stored: false,
  fingerprint: "",
  last_four: "",
  stored_at: null,
  working: null,
  checked_at: null,
  last_error: "",
  testable: true,
  storage_warning: WARNING,
};

const STORED: AdminService = {
  ...OFF,
  configured: true,
  source: "stored",
  stored: true,
  fingerprint: "a1b2c3d4e5f6",
  last_four: "1234",
  stored_at: "2026-10-31T10:00:00",
  working: true,
  checked_at: "2026-10-31T10:01:00",
};

const show = () =>
  render(
    <I18nProvider>
      <ServicesPanel />
    </I18nProvider>,
  );

const listing = (rows: AdminService[]) => ({
  services: rows,
  provider: rows.some((r) => r.configured) ? "openai" : "offline",
  enabled: rows.some((r) => r.configured),
  storage_warning: WARNING,
});

describe("the optional services", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.setItem("adobee-locale", "en");
  });

  it("says what each service is for and what the hub does without it", async () => {
    vi.spyOn(api, "adminServices").mockResolvedValue(listing([OFF]));
    show();

    expect(await screen.findByText("OpenAI")).toBeInTheDocument();
    expect(screen.getByText(OFF.purpose)).toBeInTheDocument();
    expect(screen.getByText(en["admin.services.without"].replace("{what}", OFF.without))).toBeInTheDocument();
    expect(screen.getByText(en["admin.services.off"])).toBeInTheDocument();
    expect(screen.getByText(en["admin.services.untested"])).toBeInTheDocument();
  });

  it("says where a key is stored before one is typed, and claims nothing more", async () => {
    vi.spyOn(api, "adminServices").mockResolvedValue(listing([OFF]));
    show();

    const said = await screen.findByText(en["admin.services.storage"]);
    expect(said).toBeInTheDocument();
    expect(said.textContent).toMatch(/in the clear/);
  });

  it("sends a typed key and never puts it on screen", async () => {
    vi.spyOn(api, "adminServices").mockResolvedValue(listing([OFF]));
    const set = vi.spyOn(api, "adminSetServiceKey").mockResolvedValue(STORED);
    show();

    const field = await screen.findByLabelText(en["admin.services.key"]);
    expect(field).toHaveAttribute("type", "password");
    await userEvent.type(field, "sk-secret-value-9999");
    await userEvent.click(screen.getByRole("button", { name: en["admin.services.save"] }));

    expect(set).toHaveBeenCalledWith("openai", "sk-secret-value-9999");
    expect(screen.queryByText(/sk-secret-value-9999/)).not.toBeInTheDocument();
  });

  it("shows a loaded key only as four characters and a fingerprint", async () => {
    vi.spyOn(api, "adminServices").mockResolvedValue(listing([STORED]));
    show();

    expect(
      await screen.findByText(
        en["admin.services.loaded"].replace("{tail}", "1234").replace("{fingerprint}", "a1b2c3d4e5f6"),
      ),
    ).toBeInTheDocument();
    expect(screen.getByText(en["admin.services.fromPanel"])).toBeInTheDocument();
    expect(screen.getByText(en["admin.services.works"])).toBeInTheDocument();
  });

  it("keeps a test result on screen for a key that has no stored row to write it to", async () => {
    // The environment-key case: nothing to persist the verdict against, so the answer the call
    // returned is what the operator sees. Reloading instead would say "not tested yet" after a test.
    const env = { ...OFF, configured: true, source: "environment" };
    vi.spyOn(api, "adminServices").mockResolvedValue(listing([env]));
    vi.spyOn(api, "adminCheckService").mockResolvedValue({
      ...env,
      working: true,
      checked_at: "2026-10-31T12:00:00",
    });
    show();

    await userEvent.click(await screen.findByRole("button", { name: en["admin.services.test"] }));

    expect(await screen.findByText(en["admin.services.works"])).toBeInTheDocument();
    expect(screen.queryByText(en["admin.services.untested"])).not.toBeInTheDocument();
  });

  it("tests a key on demand, not on every page load", async () => {
    vi.spyOn(api, "adminServices").mockResolvedValue(listing([STORED]));
    const check = vi.spyOn(api, "adminCheckService").mockResolvedValue(STORED);
    show();

    await screen.findByText("OpenAI");
    expect(check).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: en["admin.services.test"] }));
    expect(check).toHaveBeenCalledWith("openai");
  });

  it("says what clearing a key will do, and names the service, before it does it", async () => {
    vi.spyOn(api, "adminServices").mockResolvedValue(listing([STORED]));
    const clear = vi.spyOn(api, "adminClearServiceKey").mockResolvedValue(OFF);
    show();

    await userEvent.click(await screen.findByRole("button", { name: en["admin.services.clear"] }));

    expect(screen.getByText(en["admin.services.clearConfirm"].replace("{label}", "OpenAI"))).toBeInTheDocument();
    expect(screen.getByText(en["admin.services.clearWill"].replace("{what}", STORED.without))).toBeInTheDocument();
    expect(clear).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("button", { name: en["admin.services.clearDo"] }));
    expect(clear).toHaveBeenCalledWith("openai");
  });

  it("says a key from the environment is still a key, and where it came from", async () => {
    vi.spyOn(api, "adminServices").mockResolvedValue(listing([{ ...OFF, configured: true, source: "environment" }]));
    show();

    expect(await screen.findByText(en["admin.services.fromEnv"])).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: en["admin.services.clear"] })).not.toBeInTheDocument();
  });

  it("says a refused key was refused, with the reason the vendor gave", async () => {
    vi.spyOn(api, "adminServices").mockResolvedValue(
      listing([{ ...STORED, working: false, last_error: "AuthenticationError: 401 Incorrect API key [key]" }]),
    );
    show();

    expect(await screen.findByText(en["admin.services.fails"])).toBeInTheDocument();
    expect(screen.getByText(/401 Incorrect API key \[key\]/)).toBeInTheDocument();
  });
});
