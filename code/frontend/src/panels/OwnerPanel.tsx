import { useEffect, useState, type RefObject } from "react";
import {
  api,
  OFFLINE,
  shownError,
  mcpUrl,
  setOwnerToken,
  type Card,
  type OwnerOverview,
  type Proposal,
  type SummaryItem,
} from "../api";
import Chapter, { Frame } from "../components/Chapter";
import Composer from "../components/Composer";
import ConnectionRequests from "../components/ConnectionRequests";
import TrustBadge from "../components/TrustBadge";
import { useI18n } from "../i18n";
import type { Key } from "../i18n/en";
import { chf, day, stay } from "../lib/format";
import { demoMode } from "../lib/demo";
import { readable } from "../lib/diff";
import DemandPanel from "./DemandPanel";

// The business's side of the same booking, built like the agent chapter: the owner's input in the brief, everything
// it produces in the panel. The panel opens on the owner's dashboard; the city's demand map is one tab away.

// A miss is logged as "missing dog-friendly (asked: dog-friendly, near basel sbb)": the structured ask, never the
// traveller's own words. The studio shows the missing tags only.
const missedTags = (detail: string) =>
  detail
    .split(" (asked: ")[0]
    .split("; ")
    .filter((m) => m.startsWith("missing "))
    .map((m) => m.slice(8));
// What agents did with this card in the last 7 days, counted from the Hive's events. A hand-off from Ask the Hive
// counts as a booking: it is the business's yes-moment on any card, claimed or not.
const WEEK: [Key, string[]][] = [
  ["owner.week.shown", ["shown"]],
  ["owner.week.read", ["read"]],
  ["owner.week.booked", ["booked", "explore_handoff"]],
  ["owner.week.missed", ["missed_demand"]],
];

type T = ReturnType<typeof useI18n>["t"];
type Tab = "owner" | "demand";

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

/** One row of what agents asked this business for: who is waiting, or how often it was turned away. */
interface Ask {
  what: string;
  tags: string[];
  meta: string;
}

/** Chapter 2: the owner says what changed in plain words, checks the diff, signs, and sees the new version live. */
export default function OwnerPanel({
  initial = "hotel-rheinblick",
  sectionRef,
}: {
  initial?: string;
  sectionRef?: RefObject<HTMLElement>;
}) {
  const { t, intl } = useI18n();
  const [tab, setTab] = useState<Tab>("owner");
  const [cards, setCards] = useState<Card[]>([]);
  const [cardId, setCardId] = useState(initial);
  const [overview, setOverview] = useState<OwnerOverview | null>(null);
  // Empty until the owner speaks or picks a row under "What agents asked you for": a sample here read as a real change.
  const [instruction, setInstruction] = useState("");
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [token, setToken] = useState("");
  // The last publish: the version now live, and how many waiting agents it sent a signed offer to.
  const [published, setPublished] = useState<{ version: number; offers: number } | null>(null);
  // The backend only asks for a token when OWNER_EDIT_TOKEN is set; only then does the prompt appear.
  const needsToken = error.includes("X-Owner-Token");

  // Every business in the Hive, unclaimed ones too; refetched on focus, so a card agents just added is there.
  const loadCards = () =>
    api
      .cards()
      .then((all) => setCards([...all].sort((a, b) => a.name.localeCompare(b.name))))
      .catch(() => setCards([]));
  useEffect(() => {
    loadCards();
  }, []);
  useEffect(() => {
    setProposal(null);
    setPublished(null);
    setInstruction("");
    api
      .owner(cardId)
      .then(setOverview)
      .catch((e) => setError(shownError(e.message)));
  }, [cardId]);

  async function propose(text: string) {
    setBusy(true);
    setError("");
    setPublished(null);
    setTab("owner");
    try {
      setProposal(await api.propose(cardId, text));
      // On a phone the panel sits under the box: bring the diff into view, as the chat does with its messages.
      if (window.matchMedia?.("(max-width: 1000px)").matches)
        document.getElementById("business-tabpanel")?.scrollIntoView?.({ behavior: "smooth", block: "start" });
    } catch (e) {
      setError(shownError((e as Error).message));
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
      setPublished({ version: after.card.version, offers: after.waiting.offers_sent - offersBefore });
    } catch (e) {
      setError(shownError((e as Error).message));
    } finally {
      setBusy(false);
    }
  }

  const card = overview?.card;
  const name = card?.name ?? cards.find((c) => c.id === cardId)?.name ?? "Hotel Rheinblick";
  const unclaimed = card?.trust.claimed === false;
  // Nothing to book here (no rooms, no bookings): its yes-moment is a hand-off to the business's own site.
  const handsOff = !!overview && !overview.card.units?.length && !overview.bookings.length;
  const week = overview
    ? WEEK.map(
        ([label, kinds]) =>
          [
            handsOff && label === "owner.week.booked" ? ("owner.week.handedOff" as Key) : label,
            kinds.reduce((n, k) => n + (overview.last_7_days[k] ?? 0), 0),
          ] as const,
      )
    : [];
  // Waiting agents first: an edit wins them now. Then what agents were turned away for this week.
  const asks: Ask[] = [
    ...(overview?.waiting.asks ?? []).map((a) => ({
      what: [...a.missing, ...(a.cheaper ? [t("owner.waiting.cheaper")] : [])].join(" + "),
      tags: a.cheaper ? [] : a.missing,
      meta: [
        t("owner.waiting.agents", { n: a.agents }),
        ...(a.budget_chf > 0 ? [t("owner.waiting.budget", { chf: chf(a.budget_chf, intl) })] : []),
      ].join(" · "),
    })),
    ...(overview?.missed_demand ?? []).flatMap((m) => {
      const tags = missedTags(m.detail);
      return tags.length ? [{ what: tags.join(" + "), tags, meta: t("owner.times", { n: m.times }) }] : [];
    }),
  ];
  // Use writes the ask as the owner's own sentence and previews it straight away; nothing is live until they sign.
  const use = (tags: string[]) => {
    const text = tags.map((tag) => t("owner.waiting.add", { tag })).join(", ");
    setInstruction(text);
    propose(text);
  };

  const tabs = (
    <div className="tabs" role="tablist" aria-label={t("chapter.business")}>
      {(["owner", "demand"] as Tab[]).map((id) => (
        <button
          key={id}
          role="tab"
          id={`business-tab-${id}`}
          aria-selected={tab === id}
          aria-controls="business-tabpanel"
          className={tab === id ? "tab on" : "tab"}
          onClick={() => setTab(id)}
        >
          {t(`business.tab.${id}` as Key)}
        </button>
      ))}
    </div>
  );

  return (
    <Chapter
      id="business"
      heading="chapter.business.title"
      lead={t(unclaimed ? "chapter.business.leadUnclaimed" : "chapter.business.lead", { name })}
      sectionRef={sectionRef}
      side={
        <div className="stack">
          <div className="picker">
            <label htmlFor="business-pick">{t("owner.business")}</label>
            <select id="business-pick" value={cardId} onFocus={loadCards} onChange={(e) => setCardId(e.target.value)}>
              {cards.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
          {unclaimed ? (
            <p className="muted">{t("owner.unclaimed")}</p>
          ) : (
            <Composer
              id="owner-change"
              label={t("owner.change")}
              value={instruction}
              onChange={setInstruction}
              onSend={propose}
              busy={busy}
              placeholder={t("owner.placeholder")}
              sendLabel={card ? t("owner.previewVersion", { version: card.version + 1 }) : t("owner.preview")}
              busyLabel={t("owner.checking")}
            />
          )}
          {error && (
            <p className="error">
              {needsToken ? t("owner.tokenNeeded") : error === OFFLINE ? t("error.offline") : error}
            </p>
          )}
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
        </div>
      }
    >
      <Frame label={t("chapter.business")} head={tabs}>
        <div id="business-tabpanel" role="tabpanel" aria-labelledby={`business-tab-${tab}`} className="stack loose">
          {tab === "demand" ? (
            <DemandPanel />
          ) : (
            <>
              <div aria-live="polite">
                {proposal && (
                  <section className="change reveal stack">
                    <p className="change-summary">{summarise(proposal, t, intl)}</p>
                    {proposal.changes.length === 0 ? (
                      <p className="muted">{t("owner.noChange")}</p>
                    ) : (
                      <ul className="rows diff">
                        {proposal.changes.flatMap(readable).map((line, i) => (
                          <li key={`${line.field}/${i}`}>
                            <span className="diff-field">{line.field}</span>
                            <span className="stack tight">
                              {line.before !== undefined && <span className="diff-before">{line.before}</span>}
                              {line.after !== undefined && <span className="diff-after">{line.after}</span>}
                            </span>
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
                  </section>
                )}
                {published && (
                  <p className="published reveal">
                    {published.offers > 0
                      ? t("owner.publishedOffers", { version: published.version, n: published.offers })
                      : t("owner.published", { version: published.version })}
                  </p>
                )}
              </div>

              {week.length > 0 && (
                <dl className="kpis" role="group" aria-label={t("owner.week.title")}>
                  {week.map(([label, n]) => (
                    <div key={label}>
                      <dd className="num">{n}</dd>
                      <dt>{t(label)}</dt>
                    </div>
                  ))}
                </dl>
              )}

              {handsOff ? (
                <section className="stack">
                  <h3>{t("owner.handoffs.title")}</h3>
                  {overview.handoffs?.length ? (
                    <ul className="rows compact">
                      {overview.handoffs.map((h, i) => (
                        <li key={`${h.created_at}/${i}`} className="spread">
                          <span>{h.item}</span>
                          <span className="muted small nowrap">{day(h.created_at.slice(0, 10), intl)}</span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="muted">{t("owner.handoffs.empty")}</p>
                  )}
                </section>
              ) : (
                <section className="stack">
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
                            <td>{b.guest_name}</td>
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
              )}

              <section className="stack">
                <h3 id="owner-asked">{t("owner.asked.title")}</h3>
                {asks.length ? (
                  <ul className="rows compact" aria-labelledby="owner-asked">
                    {asks.map((a) => (
                      <li key={`${a.what}/${a.meta}`} className="spread">
                        <span className="stack tight">
                          <span>{a.what}</span>
                          <span className="muted small">{a.meta}</span>
                        </span>
                        {a.tags.length > 0 && !unclaimed && (
                          <button className="quiet" onClick={() => use(a.tags)}>
                            {t("owner.waiting.use")}
                          </button>
                        )}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">{t("owner.asked.empty")}</p>
                )}
              </section>

              <ConnectionRequests target={cardId} />

              {card && (
                <section className="stack">
                  <div className="spread">
                    <h3>{t("owner.agents.title")}</h3>
                    <span className={published ? "version fresh mono" : "version mono muted"}>v{card.version}</span>
                  </div>
                  <TrustBadge trust={card.trust} />
                  {demoMode() && (
                    <details className="presenter">
                      <summary>{t("owner.agents.mcp")}</summary>
                      <p className="muted small">
                        <code className="inline-code">{mcpUrl()}</code>
                      </p>
                      <pre>{JSON.stringify({ ...card, trust: undefined }, null, 2)}</pre>
                    </details>
                  )}
                  {demoMode() && <TamperTest card={card} />}
                </section>
              )}
            </>
          )}
        </div>
      </Frame>
    </Chapter>
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
