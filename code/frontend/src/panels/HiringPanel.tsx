import { useEffect, useId, useState } from "react";
import {
  api,
  ApiError,
  OFFLINE,
  setOwnerToken,
  shownError,
  type HiringInterview,
  type HiringMatch,
  type HiringRanked,
  type HiringShortlist,
} from "../api";
import { useI18n } from "../i18n";
import type { Key } from "../i18n/en";
import { SAMPLES } from "../lib/hiringSamples";

// Hiring, as the same story as a booking: a company posts a job, the Hive shows the people whose signed cards fit
// it, and then — only when somebody chooses to — the recruiter's agent interviews theirs. A person's agent answers
// from its owner's folder, and only if the owner said yes. Three steps on one screen, each a panel, each following
// the one before: edit the posting and the people change; start the interviews and the agents talk.

const DEBOUNCE_MS = 450;
const TURN_MS = 900;

/** The word for a verdict, with the one that has a space in it spelled the way its key is. */
const verdictKey = (v: string) => (v === "not interviewed" ? "notInterviewed" : v);

const stillRequested = () =>
  typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;

/** A score as a bar. The number is in the label, so the bar is only ever decoration. */
function Bar({ value, label }: { value: number; label: string }) {
  return (
    <span className="hire-bar" role="img" aria-label={label}>
      <i style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </span>
  );
}

/** One person the posting fits: how well, on what, and what their card does not say. */
function Candidate({ match }: { match: HiringMatch }) {
  const { t } = useI18n();
  const covered = match.evidence.filter((e) => e.covered);
  return (
    <li className="hire-cand stack tight">
      <div className="hire-cand-head">
        <strong>{match.name}</strong>
        <span className="muted small num">{t("hire.musts", { met: match.musts_met, total: match.musts_total })}</span>
        <Bar value={match.score} label={t("hire.score", { score: Math.round(match.score) })} />
        <span className="hire-score num">{Math.round(match.score)}</span>
      </div>
      {match.headline && <p className="muted small">{match.headline}</p>}
      <details>
        <summary>{t("hire.evidence")}</summary>
        <ul className="hire-evidence">
          {covered.map((e) => (
            <li key={e.requirement}>
              <span className={`hire-how ${e.how}`}>{t(`hire.how.${e.how}` as Key)}</span> <b>{e.requirement}</b>
              {e.quote && <span className="muted small"> — “{e.quote}”</span>}
            </li>
          ))}
        </ul>
      </details>
      {match.gaps.length > 0 && (
        <p className="small hire-gaps">{t("hire.gaps", { gaps: match.gaps.slice(0, 5).join(", ") })}</p>
      )}
    </li>
  );
}

/** The posting as the Hive read it: one chip per requirement, with what else counts on hover. */
function Understood({ short }: { short: HiringShortlist }) {
  const { t } = useI18n();
  const { job } = short;
  const facts = [job.min_years ? `${job.min_years}+` : "", job.location ?? "", ...job.languages].filter(Boolean);
  return (
    <div className="stack tight">
      <h3>{t("hire.understood")}</h3>
      <p className="muted small">{t("hire.understoodNote")}</p>
      <ul className="chips">
        {job.requirements.map((r) => (
          <li
            key={`${r.kind}-${r.label}`}
            className={`chip hire-chip ${r.kind}`}
            title={[
              r.options.length > 1 ? r.options.join(" · ") : "",
              r.related.length ? r.related.slice(0, 10).join(", ") : "",
            ]
              .filter(Boolean)
              .join(" — ")}
          >
            {r.label} <small>{t(`hire.kind.${r.kind}` as Key)}</small>
          </li>
        ))}
      </ul>
      {facts.length > 0 && <p className="muted small">{t("hire.facts", { facts: facts.join(", ") })}</p>}
    </div>
  );
}

export default function HiringPanel() {
  const { t } = useI18n();
  const postingId = useId();
  const [job, setJob] = useState(SAMPLES[0].text);
  const [short, setShort] = useState<HiringShortlist | null>(null);
  const [searching, setSearching] = useState(false);
  const [talk, setTalk] = useState<{ result: HiringInterview; for: string } | null>(null);
  const [running, setRunning] = useState(false);
  const [pick, setPick] = useState("");
  const [shown, setShown] = useState(0);
  const [error, setError] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const [retry, setRetry] = useState("");

  const say = (e: unknown) => {
    const message = shownError((e as Error).message);
    setError(message === OFFLINE ? t("error.offline") : message);
  };

  // The people follow the posting: every edit that stops for a moment asks the Hive who fits.
  useEffect(() => {
    if (!job.trim()) {
      setShort(null);
      return;
    }
    let live = true;
    setSearching(true);
    const timer = setTimeout(() => {
      api
        .hiringShortlist(job)
        .then((found) => live && (setShort(found), setError("")))
        .catch((e) => live && say(e))
        .finally(() => live && setSearching(false));
    }, DEBOUNCE_MS);
    return () => {
      live = false;
      clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job]);

  const interviewed = talk?.result.ranking.filter((r) => r.status === "interviewed") ?? [];
  const chosen: HiringRanked | undefined = interviewed.find((r) => r.id === pick) ?? interviewed[0];
  const turns = chosen?.transcript ?? [];

  // The agents talk one exchange at a time, unless the reader asked for less motion or presses the button.
  useEffect(() => {
    setShown(stillRequested() ? turns.length : 0);
  }, [chosen?.id, talk]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (shown >= turns.length) return;
    const timer = setTimeout(() => setShown(shown + 1), TURN_MS);
    return () => clearTimeout(timer);
  }, [shown, turns.length]);

  async function start() {
    setRunning(true);
    setError("");
    try {
      const result = await api.hiringInterview(job);
      setTalk({ result, for: job });
      setPick(result.ranking.find((r) => r.status === "interviewed")?.id ?? "");
    } catch (e) {
      say(e);
    } finally {
      setRunning(false);
    }
  }

  async function sayYes(id: string) {
    setError("");
    try {
      await api.hiringScreening(id, "yes");
      setToken(null);
      setRetry("");
      await start();
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) {
        setToken("");
        setRetry(id);
      } else say(e);
    }
  }

  const stale = talk !== null && talk.for !== job;
  const matches = short?.matches ?? [];

  return (
    <section id="hire" className="screen screen-hire" aria-labelledby="hire-title">
      <div className="screen-head">
        <h1 id="hire-title">{t("hire.title")}</h1>
        <p className="lead">{t("hire.lead")}</p>
      </div>

      <div className="hire-grid">
        <section className="panel stack" aria-labelledby="hire-step1">
          <h2 id="hire-step1">{t("hire.step1")}</h2>
          <div className="field">
            <label htmlFor="hire-sample">{t("hire.sample")}</label>
            <select
              id="hire-sample"
              defaultValue=""
              onChange={(e) => {
                const sample = SAMPLES.find((s) => s.id === e.target.value);
                if (sample) setJob(sample.text);
                e.target.value = "";
              }}
            >
              <option value="" />
              {SAMPLES.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.title}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor={postingId}>{t("hire.posting")}</label>
            <textarea
              id={postingId}
              className="hire-posting"
              rows={14}
              spellCheck={false}
              value={job}
              onChange={(e) => setJob(e.target.value)}
            />
            <p className="muted small">{t("hire.postingHint")}</p>
          </div>
          {short && <Understood short={short} />}
        </section>

        <section className="panel stack" aria-labelledby="hire-step2" aria-busy={searching}>
          <div className="spread">
            <h2 id="hire-step2">{t("hire.step2")}</h2>
            {short && <span className="muted small">{t("hire.considered", { n: short.considered })}</span>}
          </div>
          {searching && <p className="muted">{t("hire.searching")}</p>}
          {!searching && short && matches.length === 0 && <p className="muted">{t("hire.noMatch")}</p>}
          <ul className="rows hire-cands">
            {matches.map((m) => (
              <Candidate key={m.id} match={m} />
            ))}
          </ul>
          {short && short.excluded.length > 0 && (
            <p className="muted small">
              {t("hire.leftOut", {
                names: short.excluded
                  .slice(0, 8)
                  .map((e) => e.name)
                  .join(", "),
              })}
            </p>
          )}
        </section>
      </div>

      <section className="panel stack" aria-labelledby="hire-step3">
        <h2 id="hire-step3">{t("hire.step3")}</h2>
        <p className="muted">{t("hire.startHint")}</p>
        <div className="row">
          <button onClick={start} disabled={running || matches.length === 0}>
            {running ? t("hire.running") : talk ? t("hire.again") : t("hire.start")}
          </button>
          {stale && !running && <span className="status warm">{t("hire.stale")}</span>}
        </div>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}

        {talk && (
          <>
            <h3>{t("hire.consent")}</h3>
            <ul className="rows compact hire-consent">
              {talk.result.ranking.map((r) => (
                <li key={r.id} className="stack tight">
                  <div className="row">
                    <strong>{r.name}</strong>
                    <span
                      className={`status ${r.consent.state === "granted" ? "ok" : r.consent.state === "declined" ? "no" : "warm"}`}
                    >
                      {t(`hire.consent.${r.consent.state}` as Key)}
                    </span>
                    {r.consent.state === "awaiting_consent" && (
                      <button className="btn quiet" onClick={() => sayYes(r.id)} disabled={running}>
                        {t("hire.sayYes", { name: r.name })}
                      </button>
                    )}
                  </div>
                  {r.consent.granted && r.consent.granted.length > 0 && (
                    <p className="muted small">{t("hire.shared", { files: r.consent.granted.join(", ") })}</p>
                  )}
                </li>
              ))}
            </ul>
            {talk.result.ranking.some((r) => r.consent.state === "awaiting_consent") && (
              <p className="muted small">{t("hire.sayYesHint")}</p>
            )}
            {token !== null && (
              <form
                className="row"
                onSubmit={(e) => {
                  e.preventDefault();
                  setOwnerToken(token);
                  void sayYes(retry);
                }}
              >
                <label htmlFor="hire-token">{t("hire.token")}</label>
                <input id="hire-token" type="password" value={token} onChange={(e) => setToken(e.target.value)} />
                <button type="submit" disabled={!token}>
                  {t("hire.tokenSave")}
                </button>
                <span className="muted small">{t("hire.needsToken")}</span>
              </form>
            )}

            {chosen && (
              <div className="hire-talk stack">
                <div className="hire-tabs" role="group" aria-label={t("hire.consent")}>
                  {interviewed.map((r) => (
                    <button
                      key={r.id}
                      className={r.id === chosen.id ? "tab on" : "tab"}
                      aria-pressed={r.id === chosen.id}
                      onClick={() => setPick(r.id)}
                    >
                      {r.name}
                    </button>
                  ))}
                </div>
                <h3>{t("hire.talk", { name: chosen.name })}</h3>
                {chosen.read && <p className="muted small">{t("hire.opens", { files: chosen.read.join(", ") })}</p>}
                <div className="hire-stage" role="log" aria-live="polite">
                  {turns.slice(0, shown).map((turn, i) => (
                    <div key={i} className="hire-turn">
                      <div className="hire-msg ask">
                        <small>{t("hire.recruiter")}</small>
                        {turn.question}
                      </div>
                      <div className={`hire-msg reply ${turn.answer.support}`}>
                        <small>
                          {t("hire.candidate", { name: chosen.name })} ·{" "}
                          {t(`hire.support.${turn.answer.support}` as Key)}
                        </small>
                        {turn.answer.quotes.length > 0 ? (
                          <ul className="hire-quotes">
                            {turn.answer.quotes.map((q) => (
                              <li key={`${q.source}-${q.text}`}>
                                “{q.text}” <cite>{q.source}</cite>
                              </li>
                            ))}
                          </ul>
                        ) : (
                          turn.answer.text
                        )}
                      </div>
                    </div>
                  ))}
                </div>
                {shown < turns.length && (
                  <div className="row">
                    <button className="btn quiet" onClick={() => setShown(turns.length)}>
                      {t("hire.skip")}
                    </button>
                  </div>
                )}
                {shown >= turns.length && (
                  <p className="muted small">
                    {t("hire.rescored", {
                      card: Math.round(chosen.stage1_score),
                      score: Math.round(chosen.score),
                      years: chosen.years.note,
                    })}
                  </p>
                )}
              </div>
            )}
          </>
        )}
      </section>

      {talk && (
        <section className="panel stack" aria-labelledby="hire-step4">
          <h2 id="hire-step4">{t("hire.step4")}</h2>
          <ol className="rows hire-ranking">
            {talk.result.ranking.map((r) => (
              <li key={r.id} className="hire-cand-head">
                <span className="num muted">#{r.rank}</span>
                <strong>{r.name}</strong>
                <Bar value={r.score} label={t("hire.score", { score: Math.round(r.score) })} />
                <span className="hire-score num">{Math.round(r.score)}</span>
                <span className={`status ${r.verdict === "strong" ? "ok" : r.verdict === "weak" ? "no" : "warm"}`}>
                  {t(`hire.verdict.${verdictKey(r.verdict)}` as Key)}
                </span>
              </li>
            ))}
          </ol>
          <p className="muted">{t("hire.next")}</p>
        </section>
      )}
    </section>
  );
}
