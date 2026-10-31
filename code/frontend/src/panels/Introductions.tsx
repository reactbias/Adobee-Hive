import { useEffect, useId, useState, type CSSProperties } from "react";
import { api, OFFLINE, shownError, type Connection, type ScoreOutcome } from "../api";
import { useI18n } from "../i18n";
import type { Key } from "../i18n/en";
import { readCalibration, stars } from "../lib/calibration";
import { isStale, nameFor, requesterId, scoreSays } from "../lib/connect";
import { day } from "../lib/format";

// After an introduction, the hub waits for a person to say how the real meeting went. This asks, quietly and not
// as a modal, the one about to go stale first, with its deadline in view. A score is given once, in tenths of a
// star, and the answer shows what it did to the hub that carried the introduction. Nothing here when nothing waits.

const TENTHS = 50;

/** Open introductions this browser asked for. `refresh` changes when a new one was made, to read them again. */
export default function Introductions({ refresh = 0 }: { refresh?: number }) {
  const { t } = useI18n();
  const [waiting, setWaiting] = useState<Connection[]>([]);
  const heading = useId();

  useEffect(() => {
    let live = true;
    api
      .connections({ requester: requesterId() })
      .then((found) => live && setWaiting(found.awaiting_rating))
      .catch(() => live && setWaiting([]));
    return () => {
      live = false;
    };
  }, [refresh]);

  if (!waiting.length) return null;
  return (
    <section className="introductions" id="introductions" aria-labelledby={heading}>
      <div className="introductions-inner stack">
        <span className="eyebrow">{t("score.eyebrow")}</span>
        <h2 id={heading}>{t("score.title")}</h2>
        <ul className="rows">
          {waiting.map((c) => (
            <ScoreRow key={c.id} connection={c} />
          ))}
        </ul>
      </div>
    </section>
  );
}

// The hub's refusal when the 30 days are up (connections.py); it can no longer be scored, so the page stops asking.
const CLOSED = /stale|cannot be scored now/;

function ScoreRow({ connection }: { connection: Connection }) {
  const { t, intl } = useI18n();
  const [rating, setRating] = useState<number | null>(null);
  const [outcome, setOutcome] = useState<ScoreOutcome | null>(null);
  const [closed, setClosed] = useState(() => isStale(connection));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const name = nameFor(connection.target);

  async function send() {
    if (rating === null) return;
    setBusy(true);
    setError("");
    try {
      setOutcome(await api.score(connection.id, rating));
    } catch (e) {
      const message = (e as Error).message;
      if (CLOSED.test(message)) setClosed(true);
      else setError(shownError(message));
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="score-row stack tight">
      <h3>{t("score.ask", { name })}</h3>
      {outcome ? (
        <Outcome outcome={outcome} />
      ) : closed ? (
        <p className="muted">{t("score.stale")}</p>
      ) : (
        <>
          <p className="muted small">
            {t("score.deadline", { date: day(String(connection.stale_at ?? "").slice(0, 10), intl) })}
          </p>
          <Tenths value={rating} onChange={setRating} />
          <div className="row">
            <button onClick={send} disabled={busy || rating === null}>
              {t("score.send")}
            </button>
          </div>
          {error && <p className="error">{error === OFFLINE ? t("error.offline") : error}</p>}
        </>
      )}
    </li>
  );
}

/** A score from 0.0 to 5.0 in tenths: the resolution is deliberate, so it is not five whole-star buttons. */
function Tenths({ value, onChange }: { value: number | null; onChange: (tenths: number) => void }) {
  const { t, intl } = useI18n();
  const id = useId();
  const shown = value === null ? null : stars(value / 10, intl);
  return (
    <div className="tenths">
      <label htmlFor={id}>{t("score.label")}</label>
      <div className="tenths-input">
        <span
          className="star-bar"
          aria-hidden
          style={{ "--filled": `${((value ?? 0) / TENTHS) * 100}%` } as CSSProperties}
        >
          ★★★★★
        </span>
        <input
          id={id}
          type="range"
          min={0}
          max={TENTHS}
          step={1}
          value={value ?? 0}
          aria-valuetext={shown ? t("card.rating.score", { score: shown }) : undefined}
          onChange={(e) => onChange(Number(e.target.value))}
          // A press on the thumb without moving it is a choice too, so 0.0 can be given on purpose.
          onPointerUp={(e) => onChange(Number(e.currentTarget.value))}
        />
        <output htmlFor={id} className="num">
          {shown ? t("card.rating.score", { score: shown }) : "–"}
        </output>
      </div>
    </div>
  );
}

/** What the score did: the gap against what was promised, then where that leaves the hub. Lower error is better. */
function Outcome({ outcome }: { outcome: ScoreOutcome }) {
  const { t, intl } = useI18n();
  const said = scoreSays(outcome);
  const standing = outcome.hub_standing;
  const reading = standing ? readCalibration(standing.error, standing.verdict) : null;
  return (
    <div className="score-outcome stack tight" role="status">
      <p>
        {said.key === "score.done"
          ? t(said.key, { hub: said.hub, promised: stars(said.promised, intl), found: stars(said.found, intl) })
          : said.key === "score.exact"
            ? t(said.key, { hub: said.hub })
            : t(said.key)}
      </p>
      {standing && reading && (
        <p className="small">
          <span className="muted">{t("score.standing", { hub: standing.hub })}</span>{" "}
          <span className={`status ${reading.reading === "over" ? "no" : reading.reading === "unproven" ? "" : "ok"}`}>
            {t(`finder.cal.${reading.reading}` as Key, { stars: stars(reading.stars, intl) })}
          </span>
        </p>
      )}
    </div>
  );
}
