import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, setOwnerToken, type Card, type OwnerOverview, type Proposal } from "../api";
import TrustBadge from "../components/TrustBadge";
import { useI18n, useSample } from "../i18n";
import type { Key } from "../i18n/en";
import { stay } from "../lib/format";

// A miss is logged as "missing dog-friendly (asked: dog-friendly, near basel sbb)": the structured ask, never the
// traveller's own words.
function splitMiss(detail: string): [string, string] {
  const at = detail.indexOf(" (asked: ");
  return at < 0 ? [detail, ""] : [detail.slice(0, at), detail.slice(at + 9, -1)];
}
const fmt = (v: unknown) => (typeof v === "string" ? v : JSON.stringify(v));
const WEEK_LABELS: Record<string, Key> = {
  shown: "owner.week.shown",
  missed_demand: "owner.week.missed",
  booked: "owner.week.booked",
  cancelled: "owner.week.cancelled",
};

export default function OwnerStudio() {
  const { t, intl } = useI18n();
  const [cards, setCards] = useState<Card[]>([]);
  const [cardId, setCardId] = useState("hotel-rheinblick");
  const [overview, setOverview] = useState<OwnerOverview | null>(null);
  const [instruction, setInstruction] = useSample(["owner.sample"]);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [token, setToken] = useState("");
  const [published, setPublished] = useState(false);
  // The backend only asks for a token when OWNER_EDIT_TOKEN is set; only then does the prompt appear.
  const needsToken = error.includes("X-Owner-Token");

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
    setPublished(false);
    load(cardId);
  }, [cardId]);

  async function propose() {
    setBusy(true);
    setError("");
    setPublished(false);
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
      setPublished(true);
      await load(cardId);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const card = overview?.card;
  const missed = overview?.missed_demand ?? [];
  const maxMissed = Math.max(1, ...missed.map((m) => m.times));
  const week = overview ? Object.keys(WEEK_LABELS).map((k) => [k, overview.last_7_days[k] ?? 0] as const) : [];

  return (
    <div className="studio">
      <header className="page-head studio-head">
        <div className="stack">
          <span className="eyebrow">{t("owner.eyebrow")}</span>
          <h1>{t("owner.title")}</h1>
          <p className="lead">{t("owner.lead")}</p>
        </div>
        <div className="picker">
          <label htmlFor="business">{t("owner.business")}</label>
          <select id="business" value={cardId} onChange={(e) => setCardId(e.target.value)}>
            {cards.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
        </div>
      </header>

      {error && <p className="error">{needsToken ? t("owner.tokenNeeded") : error}</p>}
      {needsToken && (
        <div className="row token">
          <input
            type="password"
            placeholder={t("owner.token")}
            value={token}
            onChange={(e) => setToken(e.target.value)}
          />
          <button
            onClick={() => {
              setOwnerToken(token);
              setError("");
            }}
            disabled={!token}
          >
            {t("owner.useToken")}
          </button>
        </div>
      )}

      {week.length > 0 && (
        <dl className="kpis">
          {week.map(([k, v]) => (
            <div key={k}>
              <dd className="num">{v}</dd>
              <dt>{t(WEEK_LABELS[k])}</dt>
            </div>
          ))}
        </dl>
      )}

      <div className="grid split">
        <section className="panel stack loose">
          <div className="stack">
            <h3>{t("owner.edit.title")}</h3>
            <p className="muted">{t("owner.edit.body")}</p>
          </div>
          <textarea value={instruction} onChange={(e) => setInstruction(e.target.value)} />
          <div className="spread">
            <span className="muted">{proposal?.summary ?? (published ? t("owner.published") : "")}</span>
            <button className={proposal ? "ghost" : ""} onClick={propose} disabled={busy || !instruction.trim()}>
              {t("owner.preview")}
            </button>
          </div>
          {proposal && (
            <div className="stack reveal">
              {proposal.changes.length === 0 ? (
                <p className="muted">{t("owner.noChange")}</p>
              ) : (
                <ul className="rows diff">
                  {proposal.changes.map((c) => (
                    <li key={c.field}>
                      <span className="diff-field">{c.field}</span>
                      <span className="diff-before">{fmt(c.before)}</span>
                      <span className="diff-after">{fmt(c.after)}</span>
                    </li>
                  ))}
                </ul>
              )}
              <div className="row">
                <button onClick={publish} disabled={busy || proposal.changes.length === 0}>
                  {t("owner.publish")}
                </button>
                <button className="quiet" onClick={() => setProposal(null)}>
                  {t("owner.discard")}
                </button>
              </div>
              <p className="muted">{t("owner.publishNote")}</p>
            </div>
          )}
        </section>

        <section className="panel stack">
          <span className="eyebrow">{t("owner.missed.eyebrow")}</span>
          <h3>{t("owner.missed.title")}</h3>
          {missed.length ? (
            <ul className="rows compact meter">
              {missed.map((m) => {
                const [what, asked] = splitMiss(m.detail);
                return (
                  <li key={m.detail}>
                    <div className="spread">
                      <span>{what}</span>
                      <span className="num muted">{t("owner.times", { n: m.times })}</span>
                    </div>
                    {asked && <p className="muted clamp">“{asked}”</p>}
                    <div className="meter-track">
                      <span style={{ width: `${(m.times / maxMissed) * 100}%` }} />
                    </div>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="muted">{t("owner.missed.empty")}</p>
          )}
        </section>
      </div>

      {card && (
        <div className="grid two">
          <section className="panel stack">
            <div className="spread">
              <h3>{t("owner.agents.title")}</h3>
              <span className="mono muted">v{card.version}</span>
            </div>
            <TrustBadge trust={card.trust} />
            <pre>{JSON.stringify({ ...card, trust: undefined }, null, 2)}</pre>
            <Link className="btn quiet arrow self-start" to={`/card/${card.slug}`}>
              {t("owner.agents.human")}
            </Link>
          </section>
          <section className="panel stack">
            <h3>{t("owner.bookings.title")}</h3>
            {overview?.bookings.length ? (
              <table>
                <thead>
                  <tr>
                    <th>{t("owner.bookings.guest")}</th>
                    <th>{t("owner.bookings.dates")}</th>
                    <th className="end">CHF</th>
                  </tr>
                </thead>
                <tbody>
                  {overview.bookings.map((b) => (
                    <tr key={b.id}>
                      <td>
                        {b.guest_name}
                        <div className="muted">
                          {b.unit_id} · {b.status} · {b.agent}
                        </div>
                      </td>
                      <td className="nowrap">{stay(b.check_in, b.check_out, intl)}</td>
                      <td className="end">{b.total_chf}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <p className="muted">{t("owner.bookings.empty")}</p>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
