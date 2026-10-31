import { useState } from "react";
import { api, type AgentResult, type Booking, type Card, type Step } from "../api";
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

  // One tap on an example sends it: the page asks for clicks only where a person has to decide.
  async function send(text = input) {
    const messages = [...history, { role: "user", content: text }];
    setBusy(true);
    setError("");
    setReviewed("");
    setBooking(null);
    setHistory(messages);
    setInput("");
    const before = segments;
    setSegments([...before, { kind: "guest", text }]);
    try {
      const out = await api.agent(messages);
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
      ]);
    } catch (e) {
      setError((e as Error).message);
      setHistory(history);
      setSegments(before);
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
            <span>{t("agent.meta.noWebsite")}</span>
          </span>
        }
        pinned={
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
