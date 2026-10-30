import { useState } from "react";
import { api, type AgentResult, type Step } from "../api";

const EXAMPLES = [
  "Book me a quiet, dog-friendly hotel near Basel SBB under CHF 200 with late check-in, 2026-11-13 to 2026-11-15. My name is Tobi Muster.",
  "Two of us for Art Basel week, close to Messe Basel, parking, 3 nights from 2027-06-14. Just compare, don't book.",
  "Cheapest bed in Basel for one night, 2026-11-20 to 2026-11-21, I bring my dog.",
];

const TOOL_LABEL: Record<string, string> = {
  hive_discover: "Searched the Hive",
  hive_get_card: "Read and verified a card",
  hive_check_availability: "Checked availability",
  hive_book: "Booked",
  hive_cancel: "Cancelled",
  hive_review: "Left a verified review",
};

function StepView({ step }: { step: Step }) {
  const out = step.output as Record<string, unknown>;
  const matches = (out.matches as { name: string; score: number; why: string[] }[] | undefined) ?? [];
  const excluded = (out.excluded as { name: string; why_not: string[] }[] | undefined) ?? [];
  return (
    <li>
      <details>
        <summary>
          {TOOL_LABEL[step.tool] ?? step.tool}
          {"error" in out && <span className="chip no">{String(out.error)}</span>}
        </summary>
        {step.tool === "hive_discover" && (
          <div style={{ margin: "8px 0" }}>
            {matches.map((m) => (
              <div key={m.name}><span className="chip ok">{m.score}</span> {m.name}: {m.why.join(", ")}</div>
            ))}
            {excluded.map((e) => (
              <div key={e.name} className="muted"><span className="chip no">out</span> {e.name}: {e.why_not.join(", ")}</div>
            ))}
          </div>
        )}
        <pre>{JSON.stringify({ input: step.input, output: step.output }, null, 2)}</pre>
      </details>
    </li>
  );
}

export default function TravellerAgent() {
  const [input, setInput] = useState(EXAMPLES[0]);
  const [history, setHistory] = useState<{ role: string; content: string }[]>([]);
  const [result, setResult] = useState<AgentResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [review, setReview] = useState({ rating: 5, text: "Quiet room, the dog loved the river walk." });
  const [reviewed, setReviewed] = useState("");

  async function send() {
    const messages = [...history, { role: "user", content: input }];
    setBusy(true);
    setError("");
    setReviewed("");
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

  async function leaveReview() {
    if (!result?.booking) return;
    try {
      const r = await api.review(result.booking.receipt, review.rating, review.text);
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
          A personal agent that never opens a website. It reaches Basel businesses only through the Hive's MCP tools,
          verifies each card's signature itself, and books.
        </p>
        <div className="panel chat">
          {history.length === 0 && <p className="muted">Try one of the requests below.</p>}
          {history.map((m, i) => (
            <div key={i} className={`bubble ${m.role}`}>{m.content}</div>
          ))}
          {busy && <div className="bubble assistant">Asking the Hive...</div>}
        </div>
        <textarea value={input} onChange={(e) => setInput(e.target.value)} placeholder="Where do you want to stay?" />
        <div className="row">
          <button onClick={send} disabled={busy || !input.trim()}>Send to my agent</button>
          <button className="ghost" onClick={() => { setHistory([]); setResult(null); }}>New trip</button>
        </div>
        <div className="row">
          {EXAMPLES.map((ex) => (
            <button key={ex} className="ghost" style={{ fontSize: "0.8rem", fontWeight: 400 }} onClick={() => setInput(ex)}>
              {ex.slice(0, 48)}...
            </button>
          ))}
        </div>
        {error && <p className="error">{error}</p>}
      </section>

      <section className="stack">
        <h2>What the agent did</h2>
        {result ? (
          <>
            <p className="muted">Mode: {result.mode === "claude" ? "Claude tool use" : "offline scripted planner"}</p>
            <ul className="timeline">
              {result.steps.map((s, i) => <StepView key={i} step={s} />)}
            </ul>
          </>
        ) : (
          <p className="muted">Each MCP tool call shows up here with its input and output.</p>
        )}
        {result?.booking && (
          <div className="panel stack">
            <h3>Confirmed: {result.booking.business}</h3>
            <div>
              {result.booking.unit_name}, {result.booking.check_in} to {result.booking.check_out}, CHF {result.booking.total_chf}
            </div>
            <div className="muted">{result.booking.payment}. {result.booking.cancellation}</div>
            <label>Signed receipt (proves the stay; needed to cancel or review)</label>
            <pre style={{ maxHeight: 80 }}>{result.booking.receipt}</pre>
            <label>After the stay: leave a verified review</label>
            <div className="row">
              <select value={review.rating} onChange={(e) => setReview({ ...review, rating: Number(e.target.value) })} style={{ width: 80 }}>
                {[5, 4, 3, 2, 1].map((n) => <option key={n}>{n}</option>)}
              </select>
              <input value={review.text} onChange={(e) => setReview({ ...review, text: e.target.value })} style={{ flex: 1 }} />
              <button onClick={leaveReview}>Review</button>
            </div>
            {reviewed && <p className="muted">{reviewed}</p>}
          </div>
        )}
      </section>
    </div>
  );
}
