import { useCallback, useEffect, useId, useState, type ReactNode } from "react";
import { useI18n } from "../i18n";
import type { Key } from "../i18n/en";
import { metres, money } from "../lib/format";
import { ratingScore, type Federation, type Field, type Hit, type Price, type Scene } from "../lib/cardView";
import { connectMode, contactRows } from "../lib/connect";
import Connect from "./Connect";
import { Frame } from "./Chapter";

// A search draws one row per Card. A tap opens a Card one part at a time: who it is, then each
// offering, then the question only a person can answer, then what happens next. Details opens the whole chat.
// The cards and Details are two views of one agent run: the hold, the yes and the receipt live in the page.

const STEP_MS = 520;

const reducedMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false;

/** What the agent holds or booked for this request: the same run Details shows, never a copy of it. */
export type Deal = {
  /** The card the agent holds a booking for, waiting on the person's yes. */
  heldFor?: string;
  heldName?: string;
  /** The agent's own question with its Approve and Decline, the one Details pins under the chat. */
  gate?: ReactNode;
  /** The card the booking went to, once the person approved. */
  bookedFor?: string;
  /** The signed receipt and what comes after it. */
  receipt?: ReactNode;
  /** The agent ran and held nothing: what it said instead. */
  answer?: string;
  working: boolean;
  /** Hand this request to the agent, which holds a booking and asks again. */
  onAsk: () => void;
};

export default function GeneratedStage({
  scene,
  onDetails,
  detailsOpen = false,
  deal,
  onConnected,
}: {
  scene: Scene;
  onDetails: () => void;
  detailsOpen?: boolean;
  deal?: Deal;
  /** A connection was asked for from a row, so the introductions waiting on a score can be read again. */
  onConnected?: () => void;
}) {
  const { t } = useI18n();
  const count = scene.hits.length;
  const [shown, setShown] = useState(() => (reducedMotion() ? count : 1));
  const [drawing, setDrawing] = useState<Record<string, boolean>>({});
  const following = Object.values(drawing).some(Boolean);
  const onFollowing = useCallback(
    (id: string, pending: boolean) => setDrawing((d) => (d[id] === pending ? d : { ...d, [id]: pending })),
    [],
  );
  useEffect(() => {
    if (shown >= count) return;
    const timer = setTimeout(() => setShown((n) => n + 1), STEP_MS);
    return () => clearTimeout(timer);
  }, [shown, count]);

  return (
    <Frame
      label={t("card.stage")}
      head={
        <div className="result-head">
          <span className="result-query">{scene.query}</span>
          <div className="result-actions">
            <span className="eyebrow">
              {shown < count || following
                ? t("card.drawing")
                : count === 1
                  ? t("card.count.one")
                  : t("card.count.other", { n: count })}
            </span>
            <button className="ghost small" aria-pressed={detailsOpen} onClick={onDetails}>
              {t("card.details")}
            </button>
          </div>
        </div>
      }
    >
      {scene.federation && <Reached federation={scene.federation} />}
      {scene.hits.slice(0, shown).map((hit) => (
        <CardHit
          key={hit.card.id}
          hit={hit}
          deal={deal}
          origin={hubName(scene.federation, hit.found?.origin ?? "")}
          onFollowing={onFollowing}
          onDetails={onDetails}
          onConnected={onConnected}
        />
      ))}
    </Frame>
  );
}

/** A hub's own declared name when it was asked, else its id. */
function hubName(federation: Federation | undefined, hub: string): string {
  return federation?.asked.find((h) => h.hub === hub)?.name ?? hub;
}

/** How many hubs were asked, and any that did not answer or whose copy was refused. Shown, never swallowed. */
function Reached({ federation }: { federation: Federation }) {
  const { t } = useI18n();
  const n = federation.asked.length;
  if (federation.radius === 0) return null;
  return (
    <div className="reach-notes">
      <p>{n === 0 ? t("reach.none") : n === 1 ? t("reach.asked.one") : t("reach.asked.other", { n })}</p>
      {federation.dropped.map((d) => (
        <p key={`d:${d.hub}:${d.reason}`}>
          {d.hub === "*"
            ? t("reach.budget")
            : d.reason.startsWith("deadline")
              ? t("reach.dropped", { hub: hubName(federation, d.hub) })
              : t("reach.skipped", { hub: hubName(federation, d.hub), reason: d.reason })}
        </p>
      ))}
      {federation.rejected.map((r) => (
        <p key={`r:${r.hub}:${r.card_id}`}>{t("reach.refused", { hub: hubName(federation, r.hub) })}</p>
      ))}
    </div>
  );
}

/** Reveals `total` parts, one beat apart, once `total` is above zero. A click raises `total`. */
function useReveal(total: number): number {
  const [shown, setShown] = useState(0);
  useEffect(() => {
    if (reducedMotion() || shown >= total) return;
    const timer = setTimeout(() => setShown((n) => n + 1), STEP_MS);
    return () => clearTimeout(timer);
  }, [shown, total]);
  return reducedMotion() ? total : shown;
}

/** Identity, then the offerings list, then the searches list. A click draws the chosen file. */
function partsIn(hit: Hit): number {
  return 1 + (hit.offers.length > 0 ? 1 : 0) + (hit.needs.length > 0 ? 1 : 0);
}

/** One row until the person opens it; then its parts, one beat apart. */
function CardHit({
  hit,
  origin,
  deal,
  onFollowing,
  onDetails,
  onConnected,
}: {
  hit: Hit;
  /** The name of the hub the result came from, for a result that travelled. */
  origin: string;
  deal?: Deal;
  onFollowing: (id: string, pending: boolean) => void;
  onDetails: () => void;
  onConnected?: () => void;
}) {
  const { t, intl } = useI18n();
  const bodyId = useId();
  const { card } = hit;
  const [opened, setOpened] = useState(false);
  const [picked, setPicked] = useState<string | null>(null);
  const [listingDrawing, setListingDrawing] = useState(false);
  // The identity shows at once on open; the lists after it follow on the beat.
  const later = partsIn(hit) - 1;
  const revealed = useReveal(opened ? later : 0);
  const visible = opened ? 1 + Math.min(revealed, later) : 0;
  const pending = opened && (visible < partsIn(hit) || (picked !== null && listingDrawing));
  useEffect(() => onFollowing(card.id, pending), [card.id, pending, onFollowing]);
  const score = ratingScore(card.rating);
  const showOffers = hit.offers.length > 0 && visible >= 2;
  const showNeeds = hit.needs.length > 0 && visible >= 1 + (hit.offers.length > 0 ? 1 : 0) + 1;
  const chosen =
    hit.offers.find((o) => `offer:${o.id}` === picked) ?? hit.needs.find((n) => `search:${n.id}` === picked);
  const path = hit.found?.path ?? [];
  const why = hit.found?.why ?? [];
  const hops = hit.found?.hops ?? 0;
  const status = deal?.bookedFor === card.id ? "booked" : deal?.heldFor === card.id && !deal.bookedFor ? "held" : null;
  // What a person scans first: what kind of place, where, and from how much. Only what the card actually says.
  const cheapest = hit.offers
    .map((o) => o.price)
    .filter((p): p is Price => !!p && (p.from ?? p.amount) !== undefined)
    .sort((a, b) => (a.from ?? a.amount ?? 0) - (b.from ?? b.amount ?? 0))[0];
  const glance = [
    kindLabel(card.kind, t),
    card.place,
    cheapest ? t("card.from", { price: money(cheapest.from ?? cheapest.amount ?? 0, cheapest.currency, intl) }) : "",
  ].filter(Boolean);
  return (
    <article className={opened ? "card-hit open" : "card-hit"}>
      <div className="card-row">
        <h3>
          <button aria-expanded={opened} aria-controls={bodyId} onClick={() => setOpened((o) => !o)}>
            {card.name}
          </button>
        </h3>
        {card.tagline && <p className="card-tagline">{card.tagline}</p>}
        <p className={score === null ? "card-rating none" : "card-rating"}>
          {status && (
            <span className={`status ${status === "booked" ? "ok" : "warm"}`}>{t(`card.status.${status}`)}</span>
          )}
          {score === null ? t("card.rating.none") : <b>{t("card.rating.score", { score })}</b>}
        </p>
        <p className="card-glance">
          {glance.map((line) => (
            <span key={line}>{line}</span>
          ))}
        </p>
        {hops > 0 && origin && (
          <p className="card-from">
            {hops === 1 ? t("reach.from.one", { hub: origin }) : t("reach.from.other", { hub: origin, n: hops })}
          </p>
        )}
      </div>
      {opened && (
        <div id={bodyId} className="card-body">
          <div className="card-step">
            <span className="eyebrow">{t(card.kind === "person" ? "card.kind.person" : "card.kind.business")}</span>
            <p className="card-description">{card.description}</p>
            {(why.length > 0 || card.features.length > 0) && (
              <ul className="chips">
                {why.map((line) => (
                  <li key={`why:${line}`} className="chip match">
                    {line}
                  </li>
                ))}
                {card.features.map((feature) => (
                  <li key={`f:${feature}`} className="chip">
                    {feature}
                  </li>
                ))}
              </ul>
            )}
            {/* The place is already on the glance line above; here only what the row did not say. */}
            {(path.length > 1 || score !== null) && (
              <p className="card-meta">
                {path.length > 1 && <span>{t("card.through", { path: path.join(" → ") })}</span>}
                {score !== null && <span>{t("card.rating.count", { n: card.rating_count })}</span>}
              </p>
            )}
            <ContactList contact={card.contact} sharing={card.contactSharing} />
          </div>
          {hit.found && (
            <Connect
              entityId={card.id}
              name={card.name}
              mode={connectMode(hit.sharing, card.kind)}
              targetHub={hit.found.origin}
              card={hit.signedCard}
              onConnected={onConnected}
            />
          )}
          {showOffers && (
            <Listing
              title={t("card.offers")}
              rows={hit.offers.map((offer) => ({
                key: `offer:${offer.id}`,
                title: offer.title,
                summary: offer.summary,
                money: offer.price ? priced(offer.price, intl) : "",
              }))}
              picked={picked}
              onPick={setPicked}
            />
          )}
          {showNeeds && (
            <Listing
              title={t("card.searches")}
              rows={hit.needs.map((need) => ({
                key: `search:${need.id}`,
                title: need.title,
                summary: need.summary,
                money: need.budget ? priced(need.budget, intl) : "",
              }))}
              picked={picked}
              onPick={setPicked}
            />
          )}
          {chosen && (
            <OpenListing
              key={picked}
              listing={chosen}
              ask={hit.acting && picked?.startsWith("offer:") === true}
              cardId={card.id}
              name={card.name}
              policy={card.policy}
              deal={deal}
              onFollowing={setListingDrawing}
              onDetails={onDetails}
              onOther={() => setPicked(null)}
            />
          )}
          {visible >= partsIn(hit) && <MoreAbout name={card.name} facts={card.facts} />}
        </div>
      )}
    </article>
  );
}

/** Contact as its owner shared it: a published channel, one released on request, or not provided. */
function ContactList({ contact, sharing }: { contact: Record<string, string>; sharing: Record<string, string> }) {
  const { t } = useI18n();
  const rows = contactRows(contact, sharing);
  if (!rows.length) return null;
  return (
    <dl className="offer-fields contact">
      <dt>{t("contact.title")}</dt>
      <dd>
        <ul className="pairs">
          {rows.map((row) => (
            <li key={row.channel}>
              <span>{fieldLabel(row.channel, t)}</span>
              <span className={row.state === "shown" ? "" : "muted"}>
                {row.state === "shown"
                  ? row.value
                  : t(row.state === "onRequest" ? "contact.onRequest" : "contact.none")}
              </span>
            </li>
          ))}
        </ul>
      </dd>
    </dl>
  );
}

/** The rest of the card, folded: distances, policies, whatever the hub added. */
function MoreAbout({ name, facts }: { name: string; facts: Field[] }) {
  const { t, intl } = useI18n();
  if (!facts.length) return null;
  return (
    <details className="card-more card-step">
      <summary>{t("card.more", { name })}</summary>
      <dl className="offer-fields">
        {facts.map((field) => (
          <div key={field.key}>
            <dt>{fieldLabel(field.key, t)}</dt>
            <dd>
              {field.pairs?.length ? (
                <ul className="pairs">
                  {field.pairs.map(([label, value]) => (
                    <li key={label}>
                      <span>{label.replace(/_/g, " ")}</span>
                      <span>{typeof value === "number" && field.key.endsWith("_m") ? metres(value, intl) : value}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                field.text
              )}
            </dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

function Listing({
  title,
  rows,
  picked,
  onPick,
}: {
  title: string;
  rows: { key: string; title: string; summary?: string; money: string }[];
  picked: string | null;
  onPick: (key: string) => void;
}) {
  return (
    <section className="card-step">
      <h4>{title}</h4>
      <ul className="offer-grid">
        {rows.map((row) => (
          <li key={row.key}>
            <button className="offer-pick" aria-pressed={picked === row.key} onClick={() => onPick(row.key)}>
              <span className="offer-title">{row.title}</span>
              {row.money && <span className="offer-price">{row.money}</span>}
              {row.summary && <span className="offer-summary">{row.summary}</span>}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** The chosen file, one field at a time, then, if this request was an action, where the agent stands on it. */
function OpenListing({
  listing,
  ask,
  cardId,
  name,
  policy,
  deal,
  onFollowing,
  onDetails,
  onOther,
}: {
  listing: { title: string; fields: Field[] };
  ask: boolean;
  cardId: string;
  name: string;
  policy?: string;
  deal?: Deal;
  onFollowing: (pending: boolean) => void;
  /** Open the agent chat on this request. */
  onDetails: () => void;
  /** Back to the card's list, with nothing chosen. */
  onOther: () => void;
}) {
  const { t } = useI18n();
  const opened = useReveal(listing.fields.length + (ask ? 1 : 0));
  useEffect(
    () => onFollowing(opened < listing.fields.length + (ask ? 1 : 0)),
    [opened, listing.fields.length, ask, onFollowing],
  );
  const fields = listing.fields.slice(0, opened);
  const showAsk = ask && opened > listing.fields.length;
  return (
    <>
      {fields.length > 0 && (
        <dl className="offer-fields card-step">
          {fields.map((field) => (
            <div key={field.key}>
              <dt>{fieldLabel(field.key, t)}</dt>
              <dd>{field.text}</dd>
            </div>
          ))}
        </dl>
      )}
      {showAsk && (
        <AgentStand
          deal={deal}
          cardId={cardId}
          title={listing.title}
          name={name}
          policy={policy}
          onDetails={onDetails}
          onOther={onOther}
        />
      )}
    </>
  );
}

/**
 * Where the agent stands on this card, read from the run Details shows: the receipt once booked, its own question
 * while it holds this card, a pointer when it holds another, its answer when it held nothing, otherwise the yes
 * that hands the request to it.
 */
function AgentStand({
  deal,
  cardId,
  title,
  name,
  policy,
  onDetails,
  onOther,
}: {
  deal?: Deal;
  cardId: string;
  title: string;
  name: string;
  policy?: string;
  onDetails: () => void;
  onOther: () => void;
}) {
  const { t } = useI18n();
  if (deal?.bookedFor === cardId) return <div className="card-step">{deal.receipt}</div>;
  if (deal?.heldFor === cardId && !deal.bookedFor) return <div className="card-step">{deal.gate}</div>;
  const elsewhere = deal?.bookedFor ? undefined : deal?.heldFor && deal.heldName;
  return (
    <div className="gate card-step">
      <span className="eyebrow">{t("agent.gate.eyebrow")}</span>
      <h3>{t("card.gate", { title, name })}</h3>
      {policy && <p>{policy}</p>}
      {deal?.working ? (
        <p className="status warm" role="status">
          {t("card.asking", { name })}
        </p>
      ) : elsewhere || deal?.answer ? (
        <>
          <p>{elsewhere ? t("card.held.other", { name: elsewhere }) : deal?.answer}</p>
          <div className="row gate-actions">
            <button className="ghost" onClick={onDetails}>
              {t("card.details")}
            </button>
          </div>
        </>
      ) : (
        <div className="row gate-actions">
          <button onClick={deal?.onAsk ?? onDetails}>{t("card.yes")}</button>
          <button className="quiet" onClick={onOther}>
            {t("agent.decline")}
          </button>
        </div>
      )}
      <p className="fine">{t("card.fine")}</p>
    </div>
  );
}

/** The kind of place in the page's language, when the app has a word for it; else the card's own word. */
function kindLabel(kind: string, t: (key: Key) => string): string {
  const id = `onboard.kind.${kind}`;
  const label = t(id as Key);
  if (label !== id) return label;
  return kind === "business" ? t("card.kind.business") : kind;
}

function fieldLabel(key: string, t: (key: Key) => string): string {
  const id = `card.field.${key}`;
  const label = t(id as Key);
  return label === id ? key : label;
}

function priced(p: Price, intl: string): string {
  const unit = p.unit ? ` / ${p.unit}` : "";
  if (p.amount != null) return money(p.amount, p.currency, intl) + unit;
  if (p.from != null && p.to != null)
    return `${money(p.from, p.currency, intl)}–${money(p.to, p.currency, intl)}${unit}`;
  if (p.from != null) return money(p.from, p.currency, intl) + unit;
  return "";
}
