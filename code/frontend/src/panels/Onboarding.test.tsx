import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, type ApplicationOutcome, type DirectoryHub } from "../api";
import { I18nProvider } from "../i18n";
import en from "../i18n/en";
import * as folderPick from "../lib/folderPick";
import { canonical, fromBase64 } from "../lib/signing";
import Onboarding from "./Onboarding";

vi.mock("../lib/folderPick", async (actual) => ({
  ...(await actual<typeof import("../lib/folderPick")>()),
  canPickDirectory: () => true,
  pickDirectory: vi.fn(),
}));

const home: DirectoryHub = {
  hub: "basel.example",
  url: "",
  home: true,
  blocked: false,
  name: "Hive Basel",
  description: "",
  admission: "open",
  accepting: true,
  entities: 3,
  apply_at: "/api/hub/register",
  error: null,
  error_stars: null,
  evidence: 0,
  verdict: "unproven",
  why: "",
};

const policy = {
  policy: "open",
  means: "anything that passes the checks is admitted at once",
  checks: ["shape", "signature", "blocklist", "availability", "invite"],
  proof_types: ["dns-txt", "rel-me", "email"],
  key_custody: "Bring a public key and you keep the private half. Omit it and this hub holds one for you.",
};

const md = (path: string, text: string) => ({ path, bytes: new TextEncoder().encode(text) });
const folder = {
  folder: "Lena Hofmann",
  files: [
    md("about.md", "# Lena Hofmann\nIllustrator in Zürich.\n"),
    md("contact.md", "- email: lena@example.ch\n- phone: ask first\n"),
    md("work/offers.md", "## What I do\n- Editorial illustration — CHF 900 a piece.\n"),
    md("diary/today.md", "## What I do\n- Secret thing\n"),
  ],
};

const outcome = (over: Partial<ApplicationOutcome> = {}): ApplicationOutcome => ({
  id: "ap-1",
  state: "admitted",
  entity_id: "lena-hofmann",
  custody: "owner",
  verification: "signed",
  checks: [
    { check: "shape", ok: true, detail: "well formed" },
    { check: "signature", ok: true, detail: "signature valid: the applicant holds this key" },
  ],
  reason: "admitted automatically: this hub admits anything that passes its checks",
  next: "You are in the index and findable.",
  ...over,
});

const show = (hub = home, onBack = vi.fn()) => {
  render(
    <I18nProvider>
      <Onboarding hub={hub} onBack={onBack} onUse={vi.fn()} />
    </I18nProvider>,
  );
  return onBack;
};

const field = (name: string) => screen.getByRole("textbox", { name });

async function fromFolder() {
  vi.mocked(folderPick.pickDirectory).mockResolvedValue(folder);
  await userEvent.click(await screen.findByRole("button", { name: en["onboard.folder.pick"] }));
  await userEvent.selectOptions(await screen.findByRole("combobox", { name: "diary" }), "hidden");
  await userEvent.click(screen.getByRole("button", { name: en["onboard.folder.read"] }));
  await screen.findByRole("textbox", { name: en["onboard.card.name"] });
}

async function readyToSign() {
  await userEvent.click(await screen.findByRole("checkbox", { name: en["onboard.key.saved"] }));
}

describe("joining a hive", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.setItem("adobee-locale", "en");
    vi.spyOn(api, "registrationPolicy").mockResolvedValue(policy);
    vi.spyOn(api, "card").mockRejectedValue(new ApiError("Not Found", 404));
  });

  it("reads the hive's rules before asking for anything", async () => {
    show();
    expect(await screen.findByText(policy.means)).toBeInTheDocument();
    expect(api.registrationPolicy).toHaveBeenCalledWith("/api/hub/register");
  });

  it("asks a peer for its own rules at its own address", async () => {
    show({ ...home, home: false, apply_at: "https://zurich.example/api/hub/register" });
    await screen.findByText(policy.means);
    expect(api.registrationPolicy).toHaveBeenCalledWith("https://zurich.example/api/hub/register");
  });

  it("says plainly that the folder is read here and never uploaded", async () => {
    show();
    expect(await screen.findByText(en["onboard.folder.local"])).toBeInTheDocument();
  });

  it("fills the Card from a folder and leaves a hidden part out entirely", async () => {
    show();
    await fromFolder();

    expect(field(en["onboard.card.name"])).toHaveValue("Lena Hofmann");
    expect(field(en["onboard.card.description"])).toHaveValue("Illustrator in Zürich.");
    expect(field(en["onboard.card.id"])).toHaveValue("lena-hofmann");
    expect(screen.getByDisplayValue("Editorial illustration")).toBeInTheDocument();
    expect(screen.queryByDisplayValue("Secret thing")).toBeNull();
    expect(screen.getByDisplayValue("lena@example.ch")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: en["onboard.review.title"] }).textContent).not.toContain("diary");
  });

  it("says a shared or hidden part never appears in the Card", async () => {
    show();
    vi.mocked(folderPick.pickDirectory).mockResolvedValue(folder);
    await userEvent.click(await screen.findByRole("button", { name: en["onboard.folder.pick"] }));
    expect(await screen.findByText(en["onboard.folder.hiddenNote"])).toBeInTheDocument();
  });

  it("can be typed by hand with no folder at all, with email and phone always there", async () => {
    show();
    await userEvent.click(await screen.findByRole("button", { name: en["onboard.folder.byHand"] }));

    expect(field(en["onboard.card.name"])).toHaveValue("");
    const contact = screen.getByRole("group", { name: en["onboard.card.contact"] });
    expect(within(contact).getByText("email")).toBeInTheDocument();
    expect(within(contact).getByText("phone")).toBeInTheDocument();
  });

  it("checks the id against the hive: free when it has no card of that name, taken when it has", async () => {
    show();
    await fromFolder();
    expect(await screen.findByText(en["onboard.card.idFree"])).toBeInTheDocument();

    vi.mocked(api.card).mockResolvedValue({} as never);
    await userEvent.type(field(en["onboard.card.id"]), "x");
    expect(await screen.findByText(en["onboard.card.idTaken"])).toBeInTheDocument();
    expect(screen.getByRole("button", { name: en["onboard.sign"] })).toBeDisabled();
  });

  it("refuses an id the hive would refuse, before anything is sent", async () => {
    show();
    await fromFolder();
    await userEvent.clear(field(en["onboard.card.id"]));
    await userEvent.type(field(en["onboard.card.id"]), "Lena!");
    expect(screen.getByText(en["onboard.card.idRule"])).toBeInTheDocument();
    expect(screen.getByRole("button", { name: en["onboard.sign"] })).toBeDisabled();
  });

  it("records a proof as a claim, saying it is not checked", async () => {
    show();
    await fromFolder();
    await userEvent.click(screen.getByRole("button", { name: en["onboard.proof.add"] }));
    expect(screen.getByText(en["onboard.proof.unverified"])).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "dns-txt" })).toBeInTheDocument();
  });

  it("makes a key here, offers the private half to save, and warns what losing it means", async () => {
    show();
    await fromFolder();

    const save = await screen.findByRole("link", { name: en["onboard.key.download"] });
    expect(save.getAttribute("href")).toMatch(/^data:application\/x-pem-file/);
    expect(save).toHaveAttribute("download", "lena-hofmann.pem");
    expect(screen.getByText(en["onboard.key.loss"])).toBeInTheDocument();
    expect(screen.getByRole("button", { name: en["onboard.sign"] })).toBeDisabled();
    await readyToSign();
    expect(screen.getByRole("button", { name: en["onboard.sign"] })).toBeEnabled();
  });

  it("states the cost of letting the hive hold the key", async () => {
    show();
    await fromFolder();
    await userEvent.click(screen.getByRole("radio", { name: en["onboard.key.hub"] }));
    expect(screen.getByText(en["onboard.key.hubCost"])).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: en["onboard.key.download"] })).toBeNull();
    expect(screen.getByRole("button", { name: en["onboard.apply"] })).toBeEnabled();
  });

  it("signs exactly the document it shows, and sends only the Card", async () => {
    vi.spyOn(api, "register").mockResolvedValue(outcome());
    show();
    await fromFolder();
    await readyToSign();

    const review = screen.getByRole("region", { name: en["onboard.review.title"] });
    const shown = JSON.parse(review.querySelector("pre")!.textContent!);
    await userEvent.click(screen.getByRole("button", { name: en["onboard.sign"] }));

    await waitFor(() => expect(api.register).toHaveBeenCalled());
    const [sent, at] = vi.mocked(api.register).mock.calls[0];
    expect(at).toBe("/api/hub/register");
    const { signature, ...unsigned } = sent;
    expect(unsigned).toEqual(shown);
    expect(Object.keys(unsigned).sort()).toEqual(["entity", "invite", "proofs", "public_key"]);
    expect(JSON.stringify(sent)).not.toContain("Secret thing");

    const key = await crypto.subtle.importKey("raw", fromBase64(sent.public_key), { name: "Ed25519" }, false, [
      "verify",
    ]);
    const bytes = new TextEncoder().encode(canonical(unsigned));
    expect(await crypto.subtle.verify({ name: "Ed25519" }, key, fromBase64(signature!), bytes)).toBe(true);
  });

  it("shows an admission with what the hive checked and what to do next", async () => {
    vi.spyOn(api, "register").mockResolvedValue(outcome());
    show();
    await fromFolder();
    await readyToSign();
    await userEvent.click(screen.getByRole("button", { name: en["onboard.sign"] }));

    expect(await screen.findByRole("heading", { name: en["onboard.outcome.admitted"] })).toBeInTheDocument();
    expect(screen.getByText(outcome().reason)).toBeInTheDocument();
    expect(screen.getByText(outcome().next)).toBeInTheDocument();
    expect(screen.getByText("signature valid: the applicant holds this key")).toBeInTheDocument();
  });

  it("shows a pending application as waiting on a person", async () => {
    vi.spyOn(api, "register").mockResolvedValue(
      outcome({ state: "pending", reason: "a person reads it", next: "Check back." }),
    );
    show();
    await fromFolder();
    await readyToSign();
    await userEvent.click(screen.getByRole("button", { name: en["onboard.sign"] }));
    expect(await screen.findByRole("heading", { name: en["onboard.outcome.pending"] })).toBeInTheDocument();
    expect(screen.getByText("Check back.")).toBeInTheDocument();
  });

  it("shows a refusal as an answer with its reason and next step, never as an error", async () => {
    vi.spyOn(api, "register").mockResolvedValue(
      outcome({
        state: "rejected",
        checks: [{ check: "availability", ok: false, detail: "lena-hofmann is already registered here" }],
        reason: "lena-hofmann is already registered here",
        next: "Fix what the reason names and apply again.",
      }),
    );
    show();
    await fromFolder();
    await readyToSign();
    await userEvent.click(screen.getByRole("button", { name: en["onboard.sign"] }));

    expect(await screen.findByRole("heading", { name: en["onboard.outcome.rejected"] })).toBeInTheDocument();
    expect(screen.getAllByText("lena-hofmann is already registered here").length).toBeGreaterThan(0);
    expect(screen.getByText("Fix what the reason names and apply again.")).toBeInTheDocument();
    expect(document.querySelector(".error")).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: en["onboard.outcome.again"] }));
    expect(field(en["onboard.card.name"])).toHaveValue("Lena Hofmann");
  });

  it("leaves the way back to the Hives open on every answer, refusal included", async () => {
    // The outcome state used to render its own section without the back button, so an applicant one
    // Hive refused could reach neither the Hive list nor another Hive without reloading the page.
    vi.spyOn(api, "register").mockResolvedValue(outcome({ state: "rejected", reason: "no", next: "Try elsewhere." }));
    const onBack = show();
    await fromFolder();
    await readyToSign();
    await userEvent.click(screen.getByRole("button", { name: en["onboard.sign"] }));

    expect(await screen.findByRole("heading", { name: en["onboard.outcome.rejected"] })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: en["onboard.back"] }));
    expect(onBack).toHaveBeenCalled();
  });

  it("leads with another Hive when this one did not admit you, and never offers to use it", async () => {
    for (const state of ["rejected", "pending"] as const) {
      vi.spyOn(api, "register").mockResolvedValue(outcome({ state, reason: "not yet", next: "Wait or move on." }));
      const onBack = show();
      await fromFolder();
      await readyToSign();
      await userEvent.click(screen.getByRole("button", { name: en["onboard.sign"] }));

      expect(await screen.findByRole("heading", { name: en[`onboard.outcome.${state}`] })).toBeInTheDocument();
      // "Use this Hive" would not be true: the application was refused, or a person has yet to read it.
      expect(screen.queryByRole("button", { name: en["onboard.outcome.use"] })).not.toBeInTheDocument();
      await userEvent.click(screen.getByRole("button", { name: en["onboard.outcome.another"] }));
      expect(onBack).toHaveBeenCalled();
      cleanup();
    }
  });

  it("keeps the form when the hive cannot be reached, so nothing typed is lost", async () => {
    vi.spyOn(api, "register").mockRejectedValue(new Error("error.offline"));
    show();
    await fromFolder();
    await readyToSign();
    await userEvent.click(screen.getByRole("button", { name: en["onboard.sign"] }));
    expect(await screen.findByText(en["error.offline"])).toBeInTheDocument();
    expect(field(en["onboard.card.name"])).toHaveValue("Lena Hofmann");
  });
});
