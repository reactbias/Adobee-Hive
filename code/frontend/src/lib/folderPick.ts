import type { VaultFile } from "./folderScan";

// Reading a folder into the page. showDirectoryPicker is Chromium's; <input webkitdirectory> covers Safari and
// Firefox, so the picker is the base and the input the fallback, and no browser is turned away. Either way the
// files are read into memory here and nothing is sent anywhere.

export type PickedFolder = { folder: string; files: VaultFile[] };

/** The parts of the File System Access API this uses; not every TypeScript DOM lib carries them yet. */
interface Entry {
  kind: "file" | "directory";
  name: string;
}
interface FileEntry extends Entry {
  getFile(): Promise<File>;
}
export interface DirectoryEntry extends Entry {
  values(): AsyncIterable<Entry>;
}

/** Whether this browser can open a folder picker directly. */
export const canPickDirectory = () => typeof window !== "undefined" && "showDirectoryPicker" in window;

/** Ask for a folder with the browser's own picker. Throws if the person cancels. */
export async function pickDirectory(): Promise<PickedFolder> {
  const picker = (window as unknown as { showDirectoryPicker: () => Promise<DirectoryEntry> }).showDirectoryPicker;
  return fromHandle(await picker());
}

// .obsidian, .git and the like belong to the tools, not to the person's notes.
const skipped = (path: string) => path.split("/").some((part) => part.startsWith("."));

function read(path: string, file: File): Promise<VaultFile> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve({ path, bytes: new Uint8Array(reader.result as ArrayBuffer) });
    reader.onerror = () => reject(reader.error);
    reader.readAsArrayBuffer(file);
  });
}

/** Every file under a directory handle, with paths relative to it. */
export async function fromHandle(root: DirectoryEntry): Promise<PickedFolder> {
  const files: VaultFile[] = [];
  const walk = async (dir: DirectoryEntry, prefix: string) => {
    for await (const entry of dir.values()) {
      const path = prefix + entry.name;
      if (skipped(path)) continue;
      if (entry.kind === "directory") await walk(entry as DirectoryEntry, `${path}/`);
      else files.push(await read(path, await (entry as FileEntry).getFile()));
    }
  };
  await walk(root, "");
  return { folder: root.name, files };
}

/** The files of an `<input webkitdirectory>`, whose paths start with the folder's own name. */
export async function fromFileList(list: ArrayLike<File>): Promise<PickedFolder> {
  const all = Array.from(list);
  const folder = all[0]?.webkitRelativePath.split("/")[0] ?? "";
  const files: VaultFile[] = [];
  for (const file of all) {
    const path = file.webkitRelativePath.split("/").slice(1).join("/") || file.name;
    if (!skipped(path)) files.push(await read(path, file));
  }
  return { folder, files };
}
