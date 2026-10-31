import { useState } from "react";
import { api, MOODS, type AskItem, type AskResult, type Handoff, type Mood } from "../api";
import { useI18n } from "../i18n";
import type { Key } from "../i18n/en";
import { capitalise, day, money } from "../lib/format";

const EXAMPLES: Key[] = ["ask.ex1", "ask.ex2", "ask.ex3", "ask.ex4"];

// Ask any question about the example businesses. The mood is the person's own, visible setting: it is sent with the
// question and echoed back with its effects, and nothing here guesses it.
export default function AskPanel() {
  const { t, intl } = useI18n();
  const [question, setQuestion] = useState("");
  const [mood, setMood] = useState<Mood | null>(null);
  const [result, setResult] = useState<AskResult | null>(null);
  const [handoff, setHandoff] = useState<Handoff | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function ask(q = question) {
    if (!q.trim()) return;
    setQuestion(q);
    setBusy(true);
    setError("");
    setHandoff(null);
    try {
      setResult(await api.ask(q, mood));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function approve() {
    if (!result?.pending) return;
    try {
      setHandoff(await api.askApprove(result.pending.id));
      setResult({ ...result, pending: null });
    } catch (e) {
      setError((e as Error).message);
    }
  }

  const price = (i: AskItem) =>
    !i.price
      ? null
      : i.price.amount === 0
        ? t("ask.free")
        : t("ask.per", { price: money(i.price.amount, i.price.currency, intl), per: i.price.per });

  return (
    <div className="grid split ask">
      <section className="stack loose">
        <header className="stack">
          <h3>{t("ask.title")}</h3>
          <p className="lead">{t("ask.lead")}</p>
        </header>

        <form
          className="composer"
          onSubmit={(e) => {
            e.preventDefault();
            ask();
          }}
        >
          <label htmlFor="ask-q">{t("ask.label")}</label>
          <textarea
            id="ask-q"
            value={question}
            maxLength={500}
            placeholder={t("ask.ex1")}
            onChange={(e) => setQuestion(e.target.value)}
          />

          <fieldset className="moods">
            <legend>{t("ask.mood.label")}</legend>
            {[null, ...MOODS].map((m) => (
              <button
                type="button"
                key={m ?? "none"}
                className={m === mood ? "on" : ""}
                aria-pressed={m === mood}
                onClick={() => setMood(m)}
              >
                {t(m ? (`ask.mood.${m}` as Key) : "ask.mood.none")}
              </button>
            ))}
          </fieldset>
          <p className="fine muted">{t("ask.mood.note")}</p>

          <button type="submit" className="btn" disabled={busy || !question.trim()}>
            {busy ? t("ask.working") : t("ask.send")}
          </button>
        </form>

        <div className="examples">
          <span className="eyebrow">{t("ask.examples")}</span>
          <ul className="rows">
            {EXAMPLES.map((k) => (
              <li key={k}>
                <button type="button" className="example" onClick={() => ask(t(k))}>
                  {t(k)}
                </button>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="stack" aria-live="polite">
        {error && <p className="error">{error}</p>}
        {result && (
          <>
            <div className="panel stack">
              <span className="eyebrow">{t("ask.effects")}</span>
              <div className="statuses">
                {result.preference.mood && (
                  <span className="status ok">{t(`ask.mood.${result.preference.mood}` as Key)}</span>
                )}
                {result.preference.effects.length ? (
                  result.preference.effects.map((e) => (
                    <span key={e} className="status">
                      {t(`ask.effect.${e}` as Key)}
                    </span>
                  ))
                ) : (
                  <span className="status">{t("ask.effect.none")}</span>
                )}
              </div>
            </div>

            {result.answer && (
              <div className="panel">
                <p className="lead">{result.answer}</p>
                <p className="fine muted">{t("ask.answer.by")}</p>
              </div>
            )}

            {result.replies.length === 0 && <p className="muted">{t("ask.empty")}</p>}
            {result.replies.map((r) => (
              <article key={r.card_id} className="panel stack">
                <div className="spread">
                  <span className="eyebrow">{capitalise(r.kind)}</span>
                  <span className={`status ${r.claimed ? "ok" : "warm"}`}>
                    {r.claimed ? t("trust.signed") : t("trust.unclaimed")}
                  </span>
                </div>
                <h3>{r.name}</h3>
                <ol className="ask-items">
                  {r.items.map((i) => (
                    <li key={i.id}>
                      <h4>{i.title}</h4>
                      {i.summary && <p className="muted">{i.summary}</p>}
                      <p className="fine">
                        {[i.date && day(i.date, intl), i.duration, price(i), ...i.why].filter(Boolean).join(" · ")}
                      </p>
                    </li>
                  ))}
                </ol>
                {r.source && (
                  <p className="fine muted">
                    {t("ask.source", { url: r.source.url, date: day(r.source.read_on, intl) })}
                  </p>
                )}
              </article>
            ))}

            {result.pending && (
              <div className="panel stack">
                <h3>{t("ask.pending.title")}</h3>
                <p>{t("ask.pending.body", { business: result.pending.business, item: result.pending.item })}</p>
                <div className="row">
                  <button className="btn" onClick={approve}>
                    {t("ask.pending.approve")}
                  </button>
                  <button className="btn quiet" onClick={() => setResult({ ...result, pending: null })}>
                    {t("ask.pending.decline")}
                  </button>
                </div>
              </div>
            )}

            {result.excluded.length > 0 && (
              <div className="stack">
                <span className="eyebrow">{t("ask.excluded")}</span>
                <ul className="rows">
                  {result.excluded.map((e) => (
                    <li key={e.card_id + e.item}>
                      {e.business}, {e.item}: <span className="muted">{e.why_not.join("; ")}</span>
                    </li>
                  ))}
                </ul>
                {result.rate && <p className="fine muted">{t("ask.rate", { rate: String(result.rate.EUR_CHF) })}</p>}
              </div>
            )}

            <div className="stack">
              <span className="eyebrow">{t("ask.rules")}</span>
              <ul className="rows">
                {result.rules.map((r) => (
                  <li key={r}>{t(`ask.rule.${r}` as Key)}</li>
                ))}
              </ul>
            </div>
          </>
        )}
        {handoff && (
          <div className="panel stack">
            <p>{t("ask.handoff", { business: handoff.business })}</p>
            <a className="btn quiet arrow" href={handoff.url} target="_blank" rel="noopener noreferrer">
              {t("ask.continue", { action: handoff.action })}
            </a>
          </div>
        )}
      </section>
    </div>
  );
}
