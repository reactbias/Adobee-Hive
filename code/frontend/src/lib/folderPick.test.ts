import { describe, expect, it } from "vitest";
import { fromFileList, fromHandle } from "./folderPick";

const file = (relative: string, text: string) => {
  const f = new File([text], relative.split("/").pop()!);
  Object.defineProperty(f, "webkitRelativePath", { value: relative });
  return f;
};

describe("reading a folder in the page", () => {
  it("names the folder and keeps paths inside it, from a webkitdirectory input", async () => {
    const read = await fromFileList([file("lena/about.md", "# Lena"), file("lena/work/a.md", "x")]);
    expect(read.folder).toBe("lena");
    expect(read.files.map((f) => f.path)).toEqual(["about.md", "work/a.md"]);
    expect(new TextDecoder().decode(read.files[0].bytes)).toBe("# Lena");
  });

  it("skips an app's own dot-folders, which are not the person's notes", async () => {
    const read = await fromFileList([file("lena/.obsidian/app.md", "{}"), file("lena/about.md", "# Lena")]);
    expect(read.files.map((f) => f.path)).toEqual(["about.md"]);
  });

  it("walks a directory handle from showDirectoryPicker the same way", async () => {
    const leaf = (name: string, text: string) => ({ kind: "file", name, getFile: async () => new File([text], name) });
    const dir = (name: string, entries: unknown[]) => ({
      kind: "directory",
      name,
      values: async function* () {
        yield* entries;
      },
    });
    const root = dir("hotel", [leaf("about.md", "# Hotel"), dir("rooms", [leaf("a.md", "x")]), dir(".git", [])]);

    const read = await fromHandle(root as never);
    expect(read.folder).toBe("hotel");
    expect(read.files.map((f) => f.path).sort()).toEqual(["about.md", "rooms/a.md"]);
  });
});
