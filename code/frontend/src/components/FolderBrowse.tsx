import { useState } from "react";
import { api, OFFLINE, shownError, type FolderFile, type FolderManifest } from "../api";
import { useI18n } from "../i18n";
import { size } from "../lib/format";

/**
 * A peer's folder, browsed without an agent.
 *
 * The whole read surface is on the hub already — `/api/folders/manifest`, `/api/folders/file`, and the link
 * secret that authorises both — and the introduction response has been carrying all of it. This is the screen
 * for it: what the folder holds, how big, what type, what it hashes to, and whether this link may read it.
 *
 * Three things it has to be honest about or it lies about the product:
 *
 *  - **Listed is not served.** `folders.SERVED` is `public` and `public-summary`, and `can_read` grants only
 *    `public` without a grant, so a row the owner admits to can still answer 404. Those rows say the owner
 *    lists this and does not serve it, rather than offering a button that fails.
 *  - **Withheld is a count.** The hub never sends the names of `private` and `hidden` paths, so the line says
 *    how many there are and cannot say which.
 *  - **Unlinked shows less.** Without an established link a viewer sees only what the published Card already
 *    said; the extra the link buys is the point, so the state is on screen rather than implied.
 *
 * `secret` is a bearer token for somebody else's folder. It is a prop, not storage: it arrived in the Connect
 * response, it lives in that screen's state, and a reload loses the browse rather than parking a credential.
 */
export default function FolderBrowse({
  folder,
  secret,
  name,
}: {
  folder: FolderManifest;
  /** `folder_key.secret` from the introduction. The only time that secret exists outside a hash. */
  secret: string;
  /** The entity as the person saw it named, so the heading is about somebody rather than an id. */
  name: string;
}) {
  const { t, intl } = useI18n();
  const [shown, setShown] = useState<FolderManifest>(folder);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  async function look() {
    setBusy("look");
    setError("");
    try {
      setShown(await api.folderManifest(secret));
    } catch (e) {
      setError(shownError((e as Error).message));
    } finally {
      setBusy("");
    }
  }

  async function take(file: FolderFile) {
    setBusy(file.path);
    setError("");
    try {
      const blob = await api.folderFile(secret, file.path);
      save(blob, file.path);
    } catch (e) {
      // A refusal is always a 404, so there is nothing to say beyond "not this one".
      setError(shownError((e as Error).message));
    } finally {
      setBusy("");
    }
  }

  return (
    <section className="folder-browse stack tight">
      <div className="spread">
        <span className="eyebrow">{t("folder.eyebrow")}</span>
        <button className="quiet small" onClick={() => void look()} disabled={Boolean(busy)}>
          {t("folder.look")}
        </button>
      </div>
      <h4>{t("folder.title", { name })}</h4>
      <p className="muted small">{t(shown.linked ? "folder.linked" : "folder.unlinked")}</p>
      {shown.files.length === 0 ? (
        <p className="muted">{t("folder.nothing")}</p>
      ) : (
        <ul className="rows compact folder-rows">
          {shown.files.map((file) => (
            <li key={file.path} className="spread">
              <span className="stack tight">
                <code>{file.path}</code>
                <span className="muted small">
                  {[size(file.bytes, intl), file.media_type, file.digest].join(" · ")}
                </span>
              </span>
              <span className="row">
                {file.readable ? (
                  <button onClick={() => void take(file)} disabled={Boolean(busy)}>
                    {busy === file.path ? t("folder.taking") : t("folder.take")}
                  </button>
                ) : (
                  <span className="status" title={file.visibility}>
                    {t("folder.listedOnly")}
                  </span>
                )}
              </span>
            </li>
          ))}
        </ul>
      )}
      {shown.withheld > 0 && <p className="fine">{t("folder.withheld", { n: shown.withheld })}</p>}
      {error && <p className="error">{error === OFFLINE ? t("error.offline") : t("folder.refused")}</p>}
    </section>
  );
}

/** Hand the bytes to the browser under the file's own name. Revoked at once: the blob is already saved. */
function save(blob: Blob, path: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = path.split("/").pop() || path;
  link.click();
  URL.revokeObjectURL(url);
}
