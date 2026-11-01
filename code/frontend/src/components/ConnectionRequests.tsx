import { useEffect, useRef, useState } from "react";
import { api, OFFLINE, shownError, type Connection } from "../api";
import { useI18n } from "../i18n";

/**
 * The owner's side of an "Ask to connect": who asked for this entity, each with Accept or Decline. Accepting
 * starts the clock to score the meeting; declining ends it, and a declined request never becomes a rating.
 *
 * Nothing on this hub pushes: no websocket, no mail. So the list asks again every half minute, and a request
 * that was not there on the first answer is marked as new — otherwise an owner finds out somebody is waiting
 * only by reloading the page, which is how it read before.
 *
 * Three states, not two. Nobody waiting draws nothing, because the owner's page carries no empty headings. But
 * a hub we could not ask says so: "nobody wants to meet you" and "we could not ask" are different sentences and
 * only one of them is bad news.
 */
export default function ConnectionRequests({ target }: { target: string }) {
  const { t } = useI18n();
  const [requests, setRequests] = useState<Connection[]>([]);
  /** What the owner answered here, with the row the hub gave back. Kept so a poll cannot wipe the answer. */
  const [answered, setAnswered] = useState<Record<string, Connection>>({});
  const [unreachable, setUnreachable] = useState(false);
  const [fresh, setFresh] = useState<string[]>([]);
  const [error, setError] = useState("");
  // The ids the first answer carried. null until it arrives, so the first list is never all-new.
  const known = useRef<Set<string> | null>(null);

  useEffect(() => {
    let live = true;
    setRequests([]);
    setAnswered({});
    setUnreachable(false);
    setFresh([]);
    known.current = null;
    const read = () =>
      api
        .connections({ target })
        .then(({ awaiting_confirmation: rows }) => {
          if (!live) return;
          if (known.current === null) known.current = new Set(rows.map((r) => r.id));
          else {
            const arrived = rows.filter((r) => !known.current?.has(r.id)).map((r) => r.id);
            for (const id of arrived) known.current.add(id);
            if (arrived.length) setFresh((seen) => [...seen, ...arrived]);
          }
          setRequests(rows);
          setUnreachable(false);
        })
        .catch(() => live && setUnreachable(true));
    read();
    const timer = setInterval(read, ASK_AGAIN_MS);
    return () => {
      live = false;
      clearInterval(timer);
    };
  }, [target]);

  async function decide(id: string, accept: boolean) {
    setError("");
    try {
      const row = accept ? await api.confirmConnection(id) : await api.declineConnection(id);
      setAnswered((d) => ({ ...d, [id]: row }));
    } catch (e) {
      setError(shownError((e as Error).message));
    }
  }

  // An answered row leaves the hub's waiting list on the next poll; it stays on screen with its outcome.
  const waiting = requests.filter((r) => !answered[r.id]);
  const shown = [...waiting, ...Object.values(answered)];
  if (!shown.length && !unreachable) return null;
  return (
    <section className="stack">
      <h3>{waiting.length ? t("requests.count", { n: waiting.length }) : t("requests.title")}</h3>
      {unreachable && <p className="status no">{t("requests.unreachable")}</p>}
      {shown.length > 0 && (
        <ul className="rows compact">
          {shown.map((r) => (
            <li key={r.id} className="spread">
              <span>
                {t("requests.from", { who: r.requester })}
                {fresh.includes(r.id) && !answered[r.id] && <span className="chip match">{t("requests.new")}</span>}
              </span>
              {answered[r.id] ? (
                <span className={`status ${answered[r.id].state === "open" ? "ok" : ""}`}>
                  {t(answered[r.id].state === "open" ? "requests.accepted" : "requests.refused")}
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
      )}
      {error && <p className="error">{error === OFFLINE ? t("error.offline") : error}</p>}
    </section>
  );
}

// Half a minute: often enough that a waiting person is not left standing, cheap enough for a hub on a laptop.
const ASK_AGAIN_MS = 30_000;
