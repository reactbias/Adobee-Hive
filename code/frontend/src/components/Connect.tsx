import { useState } from "react";
import { api, OFFLINE, shownError, type Card, type Connection } from "../api";
import { useI18n } from "../i18n";
import { remember, requesterId, type ConnectMode } from "../lib/connect";
import { day } from "../lib/format";
import FolderBrowse from "./FolderBrowse";

/**
 * Ask to be introduced to a result. The label says what it will take before the click: Connect opens at once,
 * Ask to connect waits for the owner's yes and says so. An entry nobody may ask for draws nothing.
 */
export default function Connect({
  entityId,
  name,
  mode,
  targetHub = "",
  card,
  onConnected,
}: {
  entityId: string;
  name: string;
  mode: ConnectMode;
  /** The Hive the result came from, so the introduction is logged against the hub that carried it. */
  targetHub?: string;
  /**
   * The signed card, for a result this hub does not carry. Without it the hub has only the asker's word
   * for who the entity is, and refuses: an introduction to somebody on a peer is recorded here, but who
   * they are is checked against the key their own hub pinned. Must be the card the search returned, not
   * the screen's normalised copy — the signature covers the exact bytes.
   */
  card?: Card;
  onConnected?: (connection: Connection) => void;
}) {
  const { t, intl } = useI18n();
  const [made, setMade] = useState<Connection | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  if (!mode) return null;

  async function connect() {
    setBusy(true);
    setError("");
    try {
      const connection = await api.connect({
        requester: requesterId(),
        entity_id: entityId,
        ...(targetHub ? { target_hub: targetHub } : {}),
        // Sent whenever the search handed one over. The hub ignores it for an entity it carries itself,
        // so there is nothing here that has to guess which results are remote — guessing wrong is the bug.
        ...(card ? { card } : {}),
      });
      remember(entityId, name);
      setMade(connection);
      onConnected?.(connection);
    } catch (e) {
      setError(shownError((e as Error).message));
    } finally {
      setBusy(false);
    }
  }

  if (made?.state === "requested") return <p className="status warm card-step">{t("connect.waiting")}</p>;
  if (made?.state === "declined") return <p className="status no card-step">{t("connect.declined")}</p>;
  if (made)
    return (
      <div className="card-step stack tight">
        <p className="status ok">
          {t("connect.opened", { date: day(String(made.stale_at ?? "").slice(0, 10), intl) })}
        </p>
        {/* The introduction hands over the folder and the bearer for it in the same response. The hub fills
            them for an entity it carries itself and leaves them out for a remote one, so nothing is drawn
            where there is nothing to draw. The secret stays in this component's state. */}
        {made.folder && made.folder_key?.secret && (
          <FolderBrowse
            folder={made.folder}
            secret={made.folder_key.secret}
            name={name}
            away={made.remote ? made.origin_hub || made.target_hub || "" : ""}
          />
        )}
      </div>
    );
  return (
    <div className="connect card-step">
      <button onClick={connect} disabled={busy}>
        {t(mode === "now" ? "connect.now" : "connect.ask")}
      </button>
      {mode === "ask" && <p className="fine">{t("connect.askNote", { name })}</p>}
      {error && <p className="error">{error === OFFLINE ? t("error.offline") : error}</p>}
    </div>
  );
}
