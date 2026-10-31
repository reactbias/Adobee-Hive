import { useState } from "react";
import { api, type AgentResult, type Booking } from "../api";
import AgentTrace from "../components/AgentTrace";

const EXAMPLES = [
  "Book me a quiet, dog-friendly hotel near Basel SBB under CHF 200 with late check-in, 2026-11-13 to 2026-11-15. My name is Tobi Muster.",
  "Two of us for Art Basel week, close to Messe Basel, parking, 3 nights from 2027-06-14. Just compare, don't book.",
  "Cheapest bed in Basel for one night, 2026-11-20 to 2026-11-21, I bring my dog.",
];

export default function TravellerAgent() {
  const [input, setInput] = useState(EXAMPLES[0]);
  const [history, setHistory] = useState<{ role: string; content: string }[]>([]);
  const [result, setResult] = useState<AgentResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [review, setReview] = useState({ rating: 5, text: "Quiet room, the dog loved the river walk." });
  const [reviewed, setReviewed] = useState("");
  const [booking, setBooking] = useState<Booking | null>(null);

  async function send() {
    const messages = [...history, { role: "user", content: input }];
    setBusy(true);
    setError("");
    setReviewed("");
    setBooking(null);
    try {
      const out = await api.agent(messages);
      setResult(out);
      setHistory([...messages, { role: "assistant", content: out.reply }]);
      setInput("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  // The only step a human takes: say yes. The agent then sends the booking it held back.
  async function approve() {
    if (!result?.pending) return;
    setBusy(true);
    setError("");
    try {
      const done = await api.approve(result.pending);
      setResult({ ...result, steps: [...result.steps, ...done.steps], pending: null });
      setBooking(done.booking);
      setHistory((h) => [...h, { role: "assistant", content: done.reply }]);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function decline() {
    if (!result) return;
    setResult({ ...result, pending: null });
    setHistory((h) => [...h, { role: "assistant", content: "Understood, nothing booked." }]);
  }

  async function leaveReview() {
    if (!booking) return;
    try {
      const r = await api.review(booking.receipt, review.rating, review.text);
      setReviewed(`Review ${r.review_id} stored as a verified stay.`);
    } catch (e) {
      setReviewed((e as Error).message);
    }
  }

  return (
    <div className="grid two">
      <section className="stack">
        <h1>Traveller agent</h1>
        <p className="muted">
          You state the intent. Your agent talks to the businesses' side of the Hive over MCP, checks every signature
          itself and negotiates. It only books when you say yes.
        </p>
        <div className="panel chat">
          {history.length === 0 && <p className="muted">Try one of the requests below.</p>}
          {history.map((m, i) => (
            <div key={i} className={`bubble ${m.role}`}>
              {m.content}
            </div>
          ))}
          {busy && <div className="bubble assistant">Asking the Hive...</div>}
        </div>
        <textarea value={input} onChange={(e) => setInput(e.target.value)} placeholder="Where do you want to stay?" />
        <div className="row">
          <button onClick={send} disabled={busy || !input.trim()}>
            Send to my agent
          </button>
          <button
            className="ghost"
            onClick={() => {
              setHistory([]);
              setResult(null);
              setBooking(null);
            }}
          >
            New trip
          </button>
        </div>
        <div className="row">
          {EXAMPLES.map((ex) => (
            <button
              key={ex}
              className="ghost"
              style={{ fontSize: "0.8rem", fontWeight: 400 }}
              onClick={() => setInput(ex)}
            >
              {ex.slice(0, 48)}...
            </button>
          ))}
        </div>
        {error && <p className="error">{error}</p>}
      </section>

      <section className="stack">
        <h2>Agent to agent</h2>
        {result ? (
          <>
            <p className="muted">
              <span className={`chip ${result.mode === "claude" ? "ok" : ""}`}>
                {result.mode === "claude"
                  ? "this run: Claude"
                  : `this run: offline planner${result.fallback ? ` (${result.fallback})` : ""}`}
              </span>{" "}
              talking to the Hive over MCP. You only see the conversation; neither side opened a website.
            </p>
            <AgentTrace steps={result.steps} />
          </>
        ) : (
          <p className="muted">The conversation between your agent and the businesses shows up here, call by call.</p>
        )}
        {result?.pending && (
          <div className="panel stack approval">
            <h3>Your agent asks: book this?</h3>
            <div>
              {String(result.pending.input.unit_id)} at {String(result.pending.input.card_id)},{" "}
              {String(result.pending.input.check_in)} to {String(result.pending.input.check_out)}, for{" "}
              {String(result.pending.input.guest_name)}
            </div>
            {result.second_opinion && (
              <div className={result.second_opinion.verdict === "concern" ? "error" : "muted"}>
                Second opinion from {result.second_opinion.by}
                {result.second_opinion.fallback ? ` (${result.second_opinion.fallback})` : ""}:{" "}
                {result.second_opinion.verdict === "agree" ? "agrees. " : "has a concern. "}
                {result.second_opinion.note}
              </div>
            )}
            <div className="row">
              <button onClick={approve} disabled={busy}>
                Approve booking
              </button>
              <button className="ghost" onClick={decline} disabled={busy}>
                Not now
              </button>
            </div>
          </div>
        )}
        {booking && (
          <div className="panel stack">
            <h3>Confirmed: {booking.business}</h3>
            <div>
              {booking.unit_name}, {booking.check_in} to {booking.check_out}, CHF {booking.total_chf}
            </div>
            <div className="muted">
              {booking.payment}. {booking.cancellation}
            </div>
            <label>Signed receipt (proves the stay; needed to cancel or review)</label>
            <pre style={{ maxHeight: 80 }}>{booking.receipt}</pre>
            <label>After the stay: leave a verified review</label>
            <div className="row">
              <select
                value={review.rating}
                onChange={(e) => setReview({ ...review, rating: Number(e.target.value) })}
                style={{ width: 80 }}
              >
                {[5, 4, 3, 2, 1].map((n) => (
                  <option key={n}>{n}</option>
                ))}
              </select>
              <input
                value={review.text}
                onChange={(e) => setReview({ ...review, text: e.target.value })}
                style={{ flex: 1 }}
              />
              <button onClick={leaveReview}>Review</button>
            </div>
            {reviewed && <p className="muted">{reviewed}</p>}
          </div>
        )}
      </section>
    </div>
  );
}
