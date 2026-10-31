import { useState } from "react";
import { api, OFFLINE, shownError, type Connection } from "../api";
import { useI18n } from "../i18n";
import { remember, requesterId, type ConnectMode } from "../lib/connect";
import { day } from "../lib/format";

/**
 * Ask to be introduced to a result. The label says what it will take before the click: Connect opens at once,
 * Ask to connect waits for the owner's yes and says so. An entry nobody may ask for draws nothing.
 */
export default function Connect({
  entityId,
  name,
  mode,
  targetHub = "",
  onConnected,
}: {
  entityId: string;
  name: string;
  mode: ConnectMode;
  /** The Hive the result came from, so the introduction is logged against the hub that carried it. */
  targetHub?: string;
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
      <p className="status ok card-step">
        {t("connect.opened", { date: day(String(made.stale_at ?? "").slice(0, 10), intl) })}
      </p>
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
