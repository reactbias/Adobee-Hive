import { useEffect, useState } from "react";
import { api, OFFLINE, shownError, type Connection } from "../api";
import { useI18n } from "../i18n";

/**
 * The owner's side of an "Ask to connect": who asked for this entity, each with Accept or Decline. Accepting
 * starts the clock to score the meeting; declining ends it, and a declined request never becomes a rating.
 * Draws nothing when the hub cannot say, and nothing while nobody is waiting: the owner's page carries no empty
 * headings.
 */
export default function ConnectionRequests({ target }: { target: string }) {
  const { t } = useI18n();
  const [requests, setRequests] = useState<Connection[] | null>(null);
  const [decided, setDecided] = useState<Record<string, Connection["state"]>>({});
  const [error, setError] = useState("");

  useEffect(() => {
    let live = true;
    setRequests(null);
    setDecided({});
    api
      .connections({ target })
      .then((found) => live && setRequests(found.awaiting_confirmation))
      .catch(() => live && setRequests(null));
    return () => {
      live = false;
    };
  }, [target]);

  async function decide(id: string, accept: boolean) {
    setError("");
    try {
      const row = accept ? await api.confirmConnection(id) : await api.declineConnection(id);
      setDecided((d) => ({ ...d, [id]: row.state }));
    } catch (e) {
      setError(shownError((e as Error).message));
    }
  }

  if (requests === null || requests.length === 0) return null;
  return (
    <section className="stack">
      <h3>{t("requests.title")}</h3>
      <ul className="rows compact">
        {requests.map((r) => (
          <li key={r.id} className="spread">
            <span>{t("requests.from", { who: r.requester })}</span>
            {decided[r.id] ? (
              <span className={`status ${decided[r.id] === "open" ? "ok" : ""}`}>
                {t(decided[r.id] === "open" ? "requests.accepted" : "requests.refused")}
              </span>
            ) : (
              <span className="row">
                <button onClick={() => decide(r.id, true)}>{t("requests.accept")}</button>
                <button className="quiet" onClick={() => decide(r.id, false)}>
                  {t("requests.decline")}
                </button>
              </span>
            )}
          </li>
        ))}
      </ul>
      {error && <p className="error">{error === OFFLINE ? t("error.offline") : error}</p>}
    </section>
  );
}
