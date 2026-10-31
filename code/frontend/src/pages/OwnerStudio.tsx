import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Card, type OwnerOverview, type Proposal } from "../api";
import TrustBadge from "../components/TrustBadge";

const fmt = (v: unknown) => (typeof v === "string" ? v : JSON.stringify(v));

export default function OwnerStudio() {
  const [cards, setCards] = useState<Card[]>([]);
  const [cardId, setCardId] = useState("hotel-rheinblick");
  const [overview, setOverview] = useState<OwnerOverview | null>(null);
  const [instruction, setInstruction] = useState("Add sauna. The courtyard double is 165 francs from today.");
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = (id: string) =>
    api
      .owner(id)
      .then(setOverview)
      .catch((e) => setError(e.message));

  useEffect(() => {
    api.cards().then(setCards);
  }, []);
  useEffect(() => {
    setProposal(null);
    load(cardId);
  }, [cardId]);

  async function propose() {
    setBusy(true);
    setError("");
    try {
      setProposal(await api.propose(cardId, instruction));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function publish() {
    if (!proposal) return;
    setBusy(true);
    try {
      await api.publish(cardId, proposal.proposed);
      setProposal(null);
      await load(cardId);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const card = overview?.card;
  return (
    <div className="stack">
      <div className="row">
        <h1 style={{ marginRight: "auto" }}>Owner studio</h1>
        <select value={cardId} onChange={(e) => setCardId(e.target.value)} style={{ width: 280 }}>
          {cards.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </div>
      <p className="muted">
        No website to maintain. Say what changed; your agent-facing card is updated, re-signed and live for every agent.
      </p>
      {error && <p className="error">{error}</p>}

      <div className="grid two">
        <section className="panel stack">
          <h3>Tell the Hive what changed</h3>
          <textarea value={instruction} onChange={(e) => setInstruction(e.target.value)} />
          <div className="row">
            <button onClick={propose} disabled={busy || !instruction.trim()}>
              Preview change
            </button>
            {proposal && <span className="muted">{proposal.summary}</span>}
          </div>
          {proposal && (
            <div className="stack">
              {proposal.changes.length === 0 && <p className="muted">No change detected.</p>}
              {proposal.changes.map((c) => (
                <div key={c.field} className="diff">
                  <strong>{c.field}</strong>
                  <div className="before">{fmt(c.before)}</div>
                  <div className="after">{fmt(c.after)}</div>
                </div>
              ))}
              <div className="row">
                <button onClick={publish} disabled={busy || proposal.changes.length === 0}>
                  Sign and publish
                </button>
                <button className="ghost" onClick={() => setProposal(null)}>
                  Discard
                </button>
              </div>
            </div>
          )}
        </section>

        <section className="panel stack">
          <h3>What agents asked for that you don't offer</h3>
          {overview?.missed_demand.length ? (
            <table>
              <tbody>
                {overview.missed_demand.map((m) => (
                  <tr key={m.detail}>
                    <td>{m.detail}</td>
                    <td>
                      <strong>{m.times}x</strong>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="muted">Nothing missed yet. Run a few searches in the traveller agent.</p>
          )}
          <div className="row">
            {Object.entries(overview?.last_7_days ?? {}).map(([k, v]) => (
              <span key={k} className="chip">
                {k.replace("_", " ")}: {v} this week
              </span>
            ))}
          </div>
        </section>
      </div>

      {card && (
        <div className="grid two">
          <section className="panel stack">
            <h3>How agents see you (version {card.version})</h3>
            <TrustBadge trust={card.trust} />
            <div className="row">
              <Link to={`/card/${card.slug}`}>How humans see you</Link>
            </div>
            <pre>{JSON.stringify({ ...card, trust: undefined }, null, 2)}</pre>
          </section>
          <section className="panel stack">
            <h3>Bookings</h3>
            {overview?.bookings.length ? (
              <table>
                <thead>
                  <tr>
                    <th>Guest</th>
                    <th>Dates</th>
                    <th>CHF</th>
                    <th>Via</th>
                  </tr>
                </thead>
                <tbody>
                  {overview.bookings.map((b) => (
                    <tr key={b.id}>
                      <td>
                        {b.guest_name}
                        <div className="muted">
                          {b.unit_id} · {b.status}
                        </div>
                      </td>
                      <td>
                        {b.check_in} to {b.check_out}
                      </td>
                      <td>{b.total_chf}</td>
                      <td className="muted">{b.agent}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="muted">No bookings yet.</p>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
