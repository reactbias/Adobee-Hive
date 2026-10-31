import { useEffect, useState } from "react";
import { api, mcpUrl, setOwnerToken, type Card, type OwnerOverview, type Proposal, type SummaryItem } from "../api";
import TrustBadge from "../components/TrustBadge";
import Display from "../components/Display";
import { useI18n, useSample } from "../i18n";
import type { Key } from "../i18n/en";
import { chf, stay } from "../lib/format";

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

type T = ReturnType<typeof useI18n>["t"];

// Offline edits come back as items, so the summary reads in the page's language rather than the backend's English.
function summarise(p: Proposal, t: T, intl: string): string {
  if (!p.summary_items) return p.summary;
  if (!p.summary_items.length) return t("owner.summary.none");
  return p.summary_items
    .map((i: SummaryItem) =>
      i.code === "price"
        ? t("owner.summary.price", { unit: i.unit, price: chf(i.price_chf, intl) })
        : t(i.code === "added" ? "owner.summary.added" : "owner.summary.removed", { tag: i.tag }),
    )
    .join(" · ");
}

/** The owner's side of the same card: plain-language edits, signed and published, and the demand they missed. */
export default function OwnerPanel({ initial = "hotel-rheinblick" }: { initial?: string }) {
  const { t, intl } = useI18n();
  const [cards, setCards] = useState<Card[]>([]);
  const [cardId, setCardId] = useState(initial);
  const [overview, setOverview] = useState<OwnerOverview | null>(null);
  const [instruction, setInstruction] = useSample(["owner.sample"]);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [token, setToken] = useState("");
  // How many waiting agents the last publish sent a signed offer to; null until something is published.
  const [published, setPublished] = useState<number | null>(null);
  // The backend only asks for a token when OWNER_EDIT_TOKEN is set; only then does the prompt appear.
  const needsToken = error.includes("X-Owner-Token");

  const load = (id: string) =>
    api
      .owner(id)
      .then(setOverview)
      .catch((e) => setError(e.message));

  useEffect(() => {
    api
      .cards()
      .then((all) => setCards(all.filter((c) => c.trust.claimed !== false)))
      .catch(() => setCards([]));
  }, []);
  useEffect(() => {
    setProposal(null);
    setPublished(null);
    load(cardId);
  }, [cardId]);

  async function propose() {
    setBusy(true);
    setError("");
    setPublished(null);
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
      const offersBefore = overview?.waiting.offers_sent ?? 0;
      await api.publish(cardId, proposal.proposed);
      setProposal(null);
      const after = await api.owner(cardId);
      setOverview(after);
      setPublished(after.waiting.offers_sent - offersBefore);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const card = overview?.card;
  const missed = overview?.missed_demand ?? [];
  const maxMissed = Math.max(1, ...missed.map((m) => m.times));
  const waiting = overview?.waiting;
  const week = overview ? Object.keys(WEEK_LABELS).map((k) => [k, overview.last_7_days[k] ?? 0] as const) : [];

  return (
    <div className="stack loose">
      <div className="panel-head">
        <div className="stack">
          <span className="eyebrow">{t("owner.role", { name: card?.name ?? "" })}</span>
          <h3>
            <Display text={t("owner.title")} />
          </h3>
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
      </div>

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

      <section className="panel stack" aria-live="polite">
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

      <div className="grid split">
        <div className="stack loose">
          <section className="panel stack loose">
            <div className="stack">
              <h3>{t("owner.edit.title")}</h3>
              <p className="muted">{t("owner.edit.body")}</p>
            </div>
            <textarea value={instruction} onChange={(e) => setInstruction(e.target.value)} />
            <div className="spread">
              <span className="muted">
                {(proposal && summarise(proposal, t, intl)) ??
                  (published === null
                    ? ""
                    : published > 0
                      ? t("owner.publishedOffers", { n: published })
                      : t("owner.published"))}
              </span>
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
            <span className="eyebrow">{t("owner.waiting.eyebrow")}</span>
            <h3>{t("owner.waiting.title")}</h3>
            <p className="muted">{t("owner.waiting.body")}</p>
            {waiting?.asks.length ? (
              <ul className="rows compact">
                {waiting.asks.map((a) => {
                  const what = [...a.missing, ...(a.cheaper ? [t("owner.waiting.cheaper")] : [])].join(" + ");
                  return (
                    <li key={what} className="spread">
                      <div className="stack tight">
                        <span>{what}</span>
                        <span className="muted">
                          {t("owner.waiting.agents", { n: a.agents })}
                          {a.budget_chf > 0 && ` · ${t("owner.waiting.budget", { chf: chf(a.budget_chf, intl) })}`}
                        </span>
                      </div>
                      {a.missing.length > 0 && !a.cheaper && (
                        <button
                          className="quiet"
                          onClick={() =>
                            setInstruction(a.missing.map((m) => t("owner.waiting.add", { tag: m })).join(", "))
                          }
                        >
                          {t("owner.waiting.use")}
                        </button>
                      )}
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="muted">{t("owner.waiting.empty")}</p>
            )}
          </section>
        </div>

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
            <p className="muted small">
              {t("owner.agents.mcp")} <code className="inline-code">{mcpUrl()}</code>
            </p>
          </section>
          <TamperTest card={card} />
        </div>
      )}
    </div>
  );
}

/** What an agent does with every card it reads: re-check the owner's signature. Here the owner sees it fail on a copy. */
function TamperTest({ card }: { card: Card }) {
  const { t } = useI18n();
  const [verdict, setVerdict] = useState<{ original: boolean; tampered: boolean; stranger: boolean } | null>(null);

  async function run() {
    const forged: Card = JSON.parse(JSON.stringify(card));
    if (forged.units.length) forged.units[0].price_chf = 1;
    else forged.features = [...forged.features, "free breakfast"];
    // A smarter forger re-signs the changed copy with their own key; only the owner's pinned key catches that.
    const resigned = await api.forge(card.id);
    const [original, tampered, stranger] = await Promise.all([
      api.verify(card),
      api.verify(forged),
      api.verify(resigned),
    ]);
    setVerdict({
      original: original.signature_valid,
      tampered: tampered.signature_valid,
      stranger: stranger.signature_valid,
    });
  }

  return (
    <section className="panel stack tamper">
      <span className="eyebrow">{t("card.tamper.eyebrow")}</span>
      <h3>{t("card.tamper.title")}</h3>
      <p className="muted">{t("card.tamper.body")}</p>
      <button className="ghost self-start" onClick={run}>
        {card.units.length ? t("card.tamper.price") : t("card.tamper.perk")}
      </button>
      {verdict && (
        <dl className="verdicts reveal">
          <div className={verdict.original ? "ok" : "no"}>
            <dt>{t("card.tamper.original")}</dt>
            <dd>{verdict.original ? t("card.tamper.valid") : t("card.tamper.invalid")}</dd>
          </div>
          <div className={verdict.tampered ? "ok" : "no"}>
            <dt>{t("card.tamper.forged")}</dt>
            <dd>{verdict.tampered ? t("card.tamper.valid") : t("card.tamper.rejected")}</dd>
          </div>
          <div className={verdict.stranger ? "ok" : "no"}>
            <dt>{t("card.tamper.stranger")}</dt>
            <dd>{verdict.stranger ? t("card.tamper.valid") : t("card.tamper.rejected")}</dd>
          </div>
        </dl>
      )}
    </section>
  );
}
