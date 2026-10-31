import { useState } from "react";
import {
  api,
  type AgentOptions,
  type AgentResult,
  type Booking,
  type Card,
  type Refusal,
  type Step,
  type Unguarded,
} from "../api";
import GroupChat, { type Segment } from "../components/GroupChat";
import NextSteps from "../components/NextSteps";
import { namesFrom } from "../components/TraceParts";
import Display from "../components/Display";
import { useI18n, useSample } from "../i18n";
import type { Key } from "../i18n/en";
import { chf, nights, stay } from "../lib/format";
import { pickNearby } from "../lib/next";

const EXAMPLES: Key[] = ["agent.example.1", "agent.example.2", "agent.example.3"];

type Rec = Record<string, unknown>;

function lastOutput(steps: Step[], tool: string): Rec | undefined {
  return [...steps].reverse().find((s) => s.tool === tool)?.output;
}

export default function TravellerAgent() {
  const { t, intl } = useI18n();
  const [input, setInput] = useSample(EXAMPLES);
  const [history, setHistory] = useState<{ role: string; content: string }[]>([]);
  const [result, setResult] = useState<AgentResult | null>(null);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [guestName, setGuestName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [rating, setRating] = useState(5);
  const [reviewText, setReviewText] = useSample(["agent.review.sample"]);
  const [reviewed, setReviewed] = useState("");
  const [booking, setBooking] = useState<Booking | null>(null);
  const [hotel, setHotel] = useState<Card | null>(null);
  const [nearby, setNearby] = useState<ReturnType<typeof pickNearby>>(null);
  // Demo only: plant a manipulated listing, and optionally run the agent without its rules.
  const [mirror, setMirror] = useState(false);
  const [rulesOff, setRulesOff] = useState(false);

  // One tap on an example sends it: the page asks for clicks only where a person has to decide.
  async function send(text = input, base = history, off = rulesOff) {
    const messages = [...base, { role: "user", content: text }];
    const options: AgentOptions = mirror ? { scenario: "injection", rules: off ? "off" : "on" } : {};
    setBusy(true);
    setError("");
    setReviewed("");
    setBooking(null);
    setHistory(messages);
    setInput("");
    const before = base.length ? segments : [];
    setSegments([...before, { kind: "guest", text }]);
    try {
      const out = await api.agent(messages, options);
      setResult(out);
      setHistory([...messages, { role: "assistant", content: out.reply }]);
      const guest = String(out.pending?.input.guest_name ?? "").split(" ")[0];
      if (guest) setGuestName(guest);
      setSegments([
        ...before,
        { kind: "guest", text },
        ...(before.length ? [] : [{ kind: "ack" } as Segment]),
        { kind: "steps", steps: out.steps },
        ...(out.second_opinion ? [{ kind: "opinion", opinion: out.second_opinion } as Segment] : []),
        { kind: "agent", text: out.reply },
        ...(out.guard?.length ? [{ kind: "refused" } as Segment] : []),
      ]);
    } catch (e) {
      setError((e as Error).message);
      setHistory(base);
      setSegments(segments);
      setInput(messages[messages.length - 1].content);
    } finally {
      setBusy(false);
    }
  }

  // The only step a human takes: say yes. The agent then sends the booking it held back.
  async function approve() {
    if (!result?.pending) return;
    const cardId = String(result.pending.input.card_id ?? "");
    const wanted = (result.steps.find((s) => s.tool === "hive_discover")?.input.features ?? []) as string[];
    setBusy(true);
    setError("");
    try {
      const done = await api.approve(result.pending);
      setResult({ ...result, steps: [...result.steps, ...done.steps], pending: null });
      setBooking(done.booking);
      // Context for the next steps, from the Hive itself. If it is out of reach the tiles simply shrink.
      const [card, cafes] = await Promise.all([
        api.card(cardId).catch(() => null),
        api.cards("cafe").catch(() => [] as Card[]),
      ]);
      setHotel(card);
      setNearby(pickNearby(cafes, wanted));
      setHistory((h) => [...h, { role: "assistant", content: done.reply }]);
      setSegments((seg) => [
        ...seg,
        { kind: "consent" },
        { kind: "steps", steps: done.steps },
        ...(done.booking ? [{ kind: "receipt", booking: done.booking } as Segment] : []),
        { kind: "agent", text: done.reply },
        ...(done.booking ? [{ kind: "next" } as Segment] : []),
      ]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function decline() {
    if (!result) return;
    setResult({ ...result, pending: null });
    setHistory((h) => [...h, { role: "assistant", content: t("agent.declined") }]);
    setSegments((seg) => [...seg, { kind: "agent", text: t("agent.declined") }]);
  }

  // From the rules-off result: the same request, now with the agent's rules on.
  function rerunGuarded() {
    const lastAsk = [...history].reverse().find((m) => m.role === "user");
    if (!lastAsk) return;
    setRulesOff(false);
    send(lastAsk.content, [], false);
  }

  function reset() {
    setHistory([]);
    setResult(null);
    setSegments([]);
    setGuestName("");
    setBooking(null);
    setHotel(null);
    setNearby(null);
    setReviewed("");
    setError("");
  }

  async function leaveReview() {
    if (!booking) return;
    try {
      const r = await api.review(booking.receipt, rating, reviewText);
      setReviewed(t("agent.review.stored", { id: r.review_id }));
    } catch (e) {
      setReviewed((e as Error).message);
    }
  }

  const steps = result?.steps ?? [];
  const names = namesFrom(steps);
  const pending = result?.pending?.input as Rec | undefined;
  const counterpartId = String(pending?.card_id ?? lastOutput(steps, "hive_get_card")?.id ?? "");
  const counterpart = names[counterpartId] ?? t("trace.hive");

  // What the gate needs to say, taken from what the business itself answered.
  const unit = list(lastOutput(steps, "hive_check_availability")?.available_units).find(
    (u) => u.id === pending?.unit_id,
  );
  const policies = (lastOutput(steps, "hive_check_availability")?.policies ?? {}) as Record<string, string>;
  const why = (list(lastOutput(steps, "hive_discover")?.matches).find((m) => m.id === pending?.card_id)?.why ??
    []) as string[];

  return (
    <div className="agent">
      <section className="brief">
        <div className="page-head">
          <span className="eyebrow">{t("agent.eyebrow")}</span>
          <h1>
            <Display text={t("agent.title")} />
          </h1>
          <p className="lead">{t("agent.lead")}</p>
        </div>

        <div className="composer">
          <label htmlFor="intent">{history.length ? t("agent.followUp") : t("agent.intent")}</label>
          <textarea
            id="intent"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey) && input.trim() && !busy) send();
            }}
            placeholder={t("agent.placeholder")}
          />
          <div className="spread">
            <button className="quiet" onClick={reset} disabled={busy || !history.length}>
              {t("agent.newTrip")}
            </button>
            <button onClick={() => send()} disabled={busy || !input.trim()}>
              {t("agent.send")}
            </button>
          </div>
        </div>

        {history.length === 0 && (
          <div className="examples">
            <span className="eyebrow">{t("agent.try")}</span>
            <ul className="rows compact">
              {EXAMPLES.map((key) => (
                <li key={key}>
                  <button className="example" onClick={() => send(t(key))} disabled={busy}>
                    {t(key)}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
        <fieldset className="stress">
          <legend className="eyebrow">{t("agent.test.eyebrow")}</legend>
          <label className="check">
            <input
              type="checkbox"
              checked={mirror}
              disabled={busy}
              onChange={(e) => {
                setMirror(e.target.checked);
                if (!e.target.checked) setRulesOff(false);
              }}
            />
            <span>{t("agent.test.injection")}</span>
          </label>
          <label className={`check danger${mirror ? "" : " off"}`}>
            <input
              type="checkbox"
              checked={rulesOff}
              disabled={busy || !mirror}
              onChange={(e) => setRulesOff(e.target.checked)}
            />
            <span>{t("agent.test.rulesOff")}</span>
          </label>
        </fieldset>
        {error && <p className="error">{error}</p>}
      </section>

      <GroupChat
        segments={segments}
        guestName={guestName || t("chat.you")}
        pending={busy}
        meta={
          <span className="stage-meta">
            {result ? (
              <span>
                {result.mode === "claude"
                  ? t("agent.mode.claude")
                  : result.mode === "openai"
                    ? t("agent.mode.openai")
                    : t("agent.mode.offline") + (result.fallback ? ` (${result.fallback})` : "")}
              </span>
            ) : (
              <span>{t("agent.mode.ready")}</span>
            )}
            <span>{t("agent.meta.mcp")}</span>
            {result?.scenario ? <span>{t("agent.meta.mirror")}</span> : <span>{t("agent.meta.noWebsite")}</span>}
            {result?.rules === "off" && <span className="danger">{t("agent.meta.rulesOff")}</span>}
          </span>
        }
        refused={result?.guard?.length ? <Refused refusals={result.guard} /> : undefined}
        pinned={
          result?.unguarded ? (
            <RulesOff damage={result.unguarded} steps={steps} onRerun={rerunGuarded} />
          ) : (
            pending && (
              <div className="gate">
                <span className="eyebrow">{t("agent.gate.eyebrow")}</span>
                <h3>
                  {t("agent.gate.question", {
                    unit: String(unit?.name ?? pending.unit_id),
                    name: counterpart,
                  })}
                </h3>
                <dl className="facts">
                  <div>
                    <dt>{t("agent.fact.dates")}</dt>
                    <dd>{stay(pending.check_in, pending.check_out, intl)}</dd>
                  </div>
                  <div>
                    <dt>{t("agent.fact.nights")}</dt>
                    <dd>{nights(pending.check_in, pending.check_out)}</dd>
                  </div>
                  <div>
                    <dt>{t("agent.fact.guest")}</dt>
                    <dd>{String(pending.guest_name)}</dd>
                  </div>
                  {unit && (
                    <div>
                      <dt>{t("agent.fact.total")}</dt>
                      <dd>{chf(unit.total_chf, intl)}</dd>
                    </div>
                  )}
                </dl>
                {result?.second_opinion && (
                  <div className={`opinion ${result.second_opinion.verdict}`}>
                    <span className="label">
                      {t("agent.opinion.from", { by: result.second_opinion.by })}
                      {result.second_opinion.fallback ? ` (${result.second_opinion.fallback})` : ""}
                    </span>
                    <p>
                      <span className={`status ${result.second_opinion.verdict === "agree" ? "ok" : "no"}`}>
                        {t(result.second_opinion.verdict === "agree" ? "agent.opinion.agree" : "agent.opinion.concern")}
                      </span>{" "}
                      {result.second_opinion.note}
                    </p>
                  </div>
                )}
                {why.length > 0 && (
                  <div className="why">
                    <span className="label">{t("agent.gate.why")}</span>
                    <p>{why.join(" · ")}</p>
                  </div>
                )}
                <div className="row gate-actions">
                  <button onClick={approve}>{t("agent.approve")}</button>
                  <button className="quiet" onClick={decline}>
                    {t("agent.decline")}
                  </button>
                </div>
                <p className="fine">
                  {t("agent.gate.fine")}
                  {policies.cancellation ? ` ${policies.cancellation}.` : ""}
                </p>
              </div>
            )
          )
        }
        followUp={booking && <NextSteps booking={booking} hotel={hotel} nearby={nearby} />}
        receipt={
          booking && (
            <article className="receipt">
              <header className="spread">
                <span className="status ok">{t("agent.receipt.eyebrow")}</span>
                <span className="mono dim">{booking.booking_id}</span>
              </header>
              <h3>{booking.business}</h3>
              <dl className="facts">
                <div>
                  <dt>{t("agent.fact.room")}</dt>
                  <dd>{booking.unit_name}</dd>
                </div>
                <div>
                  <dt>{t("agent.fact.dates")}</dt>
                  <dd>{stay(booking.check_in, booking.check_out, intl)}</dd>
                </div>
                <div>
                  <dt>{t("agent.fact.total")}</dt>
                  <dd>{chf(booking.total_chf, intl)}</dd>
                </div>
              </dl>
              <p className="dim small">
                {booking.payment}. {booking.cancellation}
              </p>
              <div className="signature">
                <span className="label">{t("agent.receipt.signature")}</span>
                <code>{booking.receipt}</code>
              </div>
              <div className="review">
                <span className="label">{t("agent.review.title")}</span>
                <div className="stars" role="radiogroup" aria-label={t("agent.review.rating")}>
                  {[1, 2, 3, 4, 5].map((n) => (
                    <button
                      key={n}
                      role="radio"
                      aria-checked={rating === n}
                      aria-label={String(n)}
                      className={n <= rating ? "on" : ""}
                      onClick={() => setRating(n)}
                    >
                      ★
                    </button>
                  ))}
                </div>
                <div className="row">
                  <input value={reviewText} onChange={(e) => setReviewText(e.target.value)} className="field" />
                  <button className="ghost" onClick={leaveReview} disabled={!reviewText.trim()}>
                    {t("agent.review.send")}
                  </button>
                </div>
                {reviewed && <p className="dim small">{reviewed}</p>}
              </div>
            </article>
          )
        }
      />
    </div>
  );
}

const list = (v: unknown) => (Array.isArray(v) ? (v as Rec[]) : []);

/** The listings the agent refused this run, and why: kept on the stage so the human sees the attempt. */
function Refused({ refusals }: { refusals: Refusal[] }) {
  const { t } = useI18n();
  return (
    <aside className="refused">
      <span className="eyebrow">{t("agent.refused.eyebrow")}</span>
      {refusals.map((r) => (
        <div key={`${r.source}/${r.card_id}`}>
          <h4>{t("agent.refused.from", { name: r.business ?? String(r.card_id), source: r.source })}</h4>
          <ul>
            {r.codes.map((c) => (
              <li key={c}>{t(`guard.${c}` as Key)}</li>
            ))}
          </ul>
        </div>
      ))}
      <p className="fine">{t("agent.refused.fine")}</p>
    </aside>
  );
}

/** Demo only: what an agent without rules would have done. Clearly labelled; nothing here was sent. */
function RulesOff(props: { damage: Unguarded; steps: Step[]; onRerun: () => void }) {
  const { t, intl } = useI18n();
  const input = props.damage.would_call.input as Rec;
  const card = lastOutput(props.steps, "hive_get_card");
  const unit = list(card?.units).find((u) => u.id === input.unit_id);
  return (
    <div className="gate unguarded">
      <span className="eyebrow">{t("agent.unguarded.eyebrow")}</span>
      <h3>
        {t("agent.unguarded.title", {
          unit: String(unit?.name ?? input.unit_id),
          name: String(card?.name ?? input.card_id),
        })}
      </h3>
      <dl className="facts">
        <div>
          <dt>{t("agent.fact.dates")}</dt>
          <dd>{stay(input.check_in, input.check_out, intl)}</dd>
        </div>
        <div>
          <dt>{t("agent.fact.total")}</dt>
          <dd>{chf(props.damage.total_chf, intl)}</dd>
        </div>
      </dl>
      <div>
        <span className="label">{t("agent.unguarded.broken")}</span>
        <ul className="broken">
          {props.damage.broken.map((b) => (
            <li key={b.code}>
              {t(`broken.${b.code}` as Key, {
                price: chf(b.price_chf, intl),
                budget: chf(b.budget_chf, intl),
              })}
            </li>
          ))}
        </ul>
      </div>
      <div className="row gate-actions">
        <button onClick={props.onRerun}>{t("agent.unguarded.rerun")}</button>
      </div>
      <p className="fine">{t("agent.unguarded.fine")}</p>
    </div>
  );
}
