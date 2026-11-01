import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, type FolderManifest } from "../api";
import { I18nProvider } from "../i18n";
import en from "../i18n/en";
import FolderBrowse from "./FolderBrowse";

// The manifest a local introduction actually hands over, copied from a live hub: one `public` file the link may
// read, one `public-summary` file it may not, and two paths withheld by count.
const FOLDER: FolderManifest = {
  owner: "hotel-rheinblick",
  viewer: "traveller-ab12",
  linked: true,
  files: [
    {
      path: "abendkarte.pdf",
      bytes: 872,
      media_type: "application/pdf",
      digest: "sha256:417cf9153fbe",
      visibility: "public",
      ref: "hotel-rheinblick/abendkarte.pdf",
      readable: true,
    },
    {
      path: "gaeste/anreisen.csv",
      bytes: 2048,
      media_type: "text/csv",
      digest: "sha256:ecb1a975c49e",
      visibility: "public-summary",
      ref: "hotel-rheinblick/gaeste/anreisen.csv",
      readable: false,
    },
  ],
  withheld: 2,
};

function draw(folder = FOLDER) {
  render(
    <I18nProvider>
      <FolderBrowse folder={folder} secret="sec-ret" name="Hotel Rheinblick" />
    </I18nProvider>,
  );
}

describe("browsing a peer's folder", () => {
  beforeEach(() => localStorage.setItem("adobee-locale", "en"));
  afterEach(() => vi.restoreAllMocks());

  it("lists each file with its size, type and digest", () => {
    draw();
    expect(screen.getByText(en["folder.title"].replace("{name}", "Hotel Rheinblick"))).toBeInTheDocument();
    expect(screen.getByText("abendkarte.pdf")).toBeInTheDocument();
    const row = screen.getByText("abendkarte.pdf").closest("li");
    expect(row).toHaveTextContent("872 B");
    expect(row).toHaveTextContent("application/pdf");
    expect(row).toHaveTextContent("sha256:417cf9153fbe");
  });

  // folders.SERVED admits a path to the manifest that can_read still refuses, so a button on every row would
  // offer dead ones.
  it("offers a download only where the link may actually read, and says so where it may not", () => {
    draw();
    expect(screen.getAllByRole("button", { name: en["folder.take"] })).toHaveLength(1);
    const withheldRow = screen.getByText("gaeste/anreisen.csv").closest("li");
    expect(withheldRow).toHaveTextContent(en["folder.listedOnly"]);
  });

  it("counts what the owner keeps back, because the hub never sends those names", () => {
    draw();
    expect(screen.getByText(en["folder.withheld"].replace("{n}", "2"))).toBeInTheDocument();
    expect(screen.queryByText(/private|hidden/)).not.toBeInTheDocument();
  });

  it("asks for the file with the link secret, and saves it under its own name", async () => {
    const read = vi.spyOn(api, "folderFile").mockResolvedValue(new Blob(["x"]));
    const url = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:x");
    const revoke = vi.spyOn(URL, "revokeObjectURL");
    // jsdom does not navigate, and a real click on a blob: href only logs that it will not.
    const clicked: { href: string; download: string }[] = [];
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      clicked.push({ href: this.getAttribute("href") ?? "", download: this.download });
    });
    draw();
    fireEvent.click(screen.getByRole("button", { name: en["folder.take"] }));
    await vi.waitFor(() => expect(read).toHaveBeenCalledWith("sec-ret", "abendkarte.pdf"));
    expect(url).toHaveBeenCalled();
    expect(clicked).toEqual([{ href: "blob:x", download: "abendkarte.pdf" }]);
    expect(revoke).toHaveBeenCalledWith("blob:x");
  });

  it("says the file was not handed over, without pretending to know why", async () => {
    vi.spyOn(api, "folderFile").mockRejectedValue(new ApiError("No such file here, or none this link may read.", 404));
    draw();
    fireEvent.click(screen.getByRole("button", { name: en["folder.take"] }));
    expect(await screen.findByText(en["folder.refused"])).toBeInTheDocument();
  });

  it("reads the manifest again, so a grant made while you were looking shows up", async () => {
    const again = vi.spyOn(api, "folderManifest").mockResolvedValue({
      ...FOLDER,
      files: FOLDER.files.map((f) => ({ ...f, readable: true })),
      withheld: 0,
    });
    draw();
    fireEvent.click(screen.getByRole("button", { name: en["folder.look"] }));
    await vi.waitFor(() => expect(again).toHaveBeenCalledWith("sec-ret"));
    await vi.waitFor(() => expect(screen.getAllByRole("button", { name: en["folder.take"] })).toHaveLength(2));
    expect(screen.queryByText(en["folder.withheld"].replace("{n}", "2"))).not.toBeInTheDocument();
  });

  it("says a link buys more than the published card did", () => {
    draw();
    expect(screen.getByText(en["folder.linked"])).toBeInTheDocument();
  });

  it("says when the folder holds nothing this viewer may see", () => {
    draw({ ...FOLDER, linked: false, files: [], withheld: 0 });
    expect(screen.getByText(en["folder.nothing"])).toBeInTheDocument();
    expect(screen.getByText(en["folder.unlinked"])).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: en["folder.take"] })).not.toBeInTheDocument();
  });

  // hub.connect computes the manifest against this hub's own folder root, so an entity on a peer comes back
  // with an empty one. "Nothing in it" would be a claim about their folder that this hub cannot make.
  it("says a remote folder is on the other hub rather than calling it empty", () => {
    render(
      <I18nProvider>
        <FolderBrowse folder={{ ...FOLDER, files: [], withheld: 0 }} secret="sec-ret" name="Lena" away="bern" />
      </I18nProvider>,
    );
    expect(screen.getByText(en["folder.away"].replace("{hub}", "bern"))).toBeInTheDocument();
    expect(screen.queryByText(en["folder.nothing"])).not.toBeInTheDocument();
    // The link is real and this hub still has nothing to show, so "you see more than the card said" would lie.
    expect(screen.queryByText(en["folder.linked"])).not.toBeInTheDocument();
  });
});
