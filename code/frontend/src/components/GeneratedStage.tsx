import { useEffect, useState } from "react";
import { useI18n } from "../i18n";
import type { Key } from "../i18n/en";
import { money } from "../lib/format";
import { ratingScore, type Field, type Hit, type Price, type Scene } from "../lib/cardView";
import { Frame } from "./Chapter";

// A search draws a Card one part at a time: who it is, then each offering, then the question
// only a person can answer. Details opens the whole chat.

const STEP_MS = 520;

const reducedMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

export default function GeneratedStage({ scene, onDetails }: { scene: Scene; onDetails: () => void }) {
  const { t } = useI18n();
  const total = scene.hits.reduce((n, hit) => n + partsIn(hit), 0);
  const [shown, setShown] = useState(() => (reducedMotion() ? total : 1));
  const [following, setFollowing] = useState(false);
  useEffect(() => {
    if (shown >= total) return;
    const timer = setTimeout(() => setShown((n) => n + 1), STEP_MS);
    return () => clearTimeout(timer);
  }, [shown, total]);

  let rest = shown;
  return (
    <Frame
      label={t("card.stage")}
      head={
        <div className="spread">
          <span className="eyebrow">{shown < total || following ? t("card.drawing") : t("card.found")}</span>
          <button className="quiet" onClick={onDetails}>
            {t("card.details")}
          </button>
        </div>
      }
    >
      {scene.hits.map((hit) => {
        const count = partsIn(hit);
        const visible = Math.max(0, Math.min(rest, count));
        rest -= count;
        return <CardHit key={hit.card.id} hit={hit} visible={visible} onFollowing={setFollowing} />;
      })}
    </Frame>
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

function CardHit({
  hit,
  visible,
  onFollowing,
}: {
  hit: Hit;
  visible: number;
  onFollowing: (pending: boolean) => void;
}) {
  const { t, intl } = useI18n();
  const [picked, setPicked] = useState<string | null>(null);
  useEffect(() => {
    if (!picked) onFollowing(false);
  }, [picked, onFollowing]);
  if (visible < 1) return null;
  const { card } = hit;
  const score = ratingScore(card.rating);
  const showOffers = hit.offers.length > 0 && visible >= 2;
  const showNeeds = hit.needs.length > 0 && visible >= 1 + (hit.offers.length > 0 ? 1 : 0) + 1;
  const chosen =
    hit.offers.find((o) => `offer:${o.id}` === picked) ?? hit.needs.find((n) => `search:${n.id}` === picked);
  return (
    <article className="card-hit">
      <div className="card-step">
        <span className="eyebrow">{t(card.kind === "person" ? "card.kind.person" : "card.kind.business")}</span>
        <h3>{card.name}</h3>
        {score === null ? (
          <p className="card-rating none">{t("card.rating.none")}</p>
        ) : (
          <p className="card-rating">
            <b>{t("card.rating.score", { score })}</b>
            <span className="dim"> {t("card.rating.count", { n: card.rating_count })}</span>
          </p>
        )}
        <p>{card.description}</p>
        {hit.found && hit.found.path.length > 0 && (
          <p className="dim">{t("card.through", { path: hit.found.path.join(" → ") })}</p>
        )}
        {hit.found?.why.map((line) => (
          <p key={line} className="dim">
            {line}
          </p>
        ))}
        {card.facts.length > 0 && (
          <dl className="offer-fields">
            {card.facts.map((field) => (
              <div key={field.key}>
                <dt>{fieldLabel(field.key, t)}</dt>
                <dd>{field.text}</dd>
              </div>
            ))}
          </dl>
        )}
      </div>
      {showOffers && (
        <Listing
          title={t("card.offers")}
          rows={hit.offers.map((offer) => ({
            key: `offer:${offer.id}`,
            title: offer.title,
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
          name={card.name}
          policy={card.policy}
          onFollowing={onFollowing}
        />
      )}
    </article>
  );
}

function Listing({
  title,
  rows,
  picked,
  onPick,
}: {
  title: string;
  rows: { key: string; title: string; money: string }[];
  picked: string | null;
  onPick: (key: string) => void;
}) {
  return (
    <section className="card-step">
      <h4>{title}</h4>
      <ul className="ask-items">
        {rows.map((row) => (
          <li key={row.key}>
            <button className="quiet offer-pick" aria-pressed={picked === row.key} onClick={() => onPick(row.key)}>
              <span>{row.title}</span>
              {row.money && <span className="fine">{row.money}</span>}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** The chosen file, one field at a time, then the yes if this request was an action. */
function OpenListing({
  listing,
  ask,
  name,
  policy,
  onFollowing,
}: {
  listing: { title: string; fields: Field[] };
  ask: boolean;
  name: string;
  policy?: string;
  onFollowing: (pending: boolean) => void;
}) {
  const { t } = useI18n();
  const [decision, setDecision] = useState<"open" | "yes" | "no">("open");
  const [given, setGiven] = useState<number | null>(null);
  const opened = useReveal(listing.fields.length + (ask ? 1 : 0));
  const afterYes = useReveal(decision === "yes" ? 2 : 0);
  const afterNo = useReveal(decision === "no" ? 1 : 0);
  const afterRate = useReveal(given === null ? 0 : 1);
  useEffect(() => {
    const pending =
      opened < listing.fields.length + (ask ? 1 : 0) ||
      (decision === "yes" && afterYes < 2) ||
      (decision === "no" && afterNo < 1) ||
      (given !== null && afterRate < 1);
    onFollowing(pending);
  }, [opened, listing.fields.length, ask, decision, afterYes, afterNo, given, afterRate, onFollowing]);
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
        <div className="gate card-step">
          <span className="eyebrow">{t("agent.gate.eyebrow")}</span>
          <h3>{t("card.gate", { title: listing.title, name })}</h3>
          {policy && <p>{policy}</p>}
          {decision === "open" && (
            <div className="row gate-actions">
              <button onClick={() => setDecision("yes")}>{t("card.yes")}</button>
              <button className="quiet" onClick={() => setDecision("no")}>
                {t("agent.decline")}
              </button>
            </div>
          )}
          <p className="fine">{t("card.fine")}</p>
          {decision === "yes" && afterYes >= 1 && <p className="status ok card-step">{t("card.yes.done")}</p>}
          {decision === "yes" && afterYes >= 2 && (
            <div className="card-step">
              <span className="label">{t("card.rate.ask")}</span>
              <div className="stars" role="radiogroup" aria-label={t("card.rate.ask")}>
                {[1, 2, 3, 4, 5].map((n) => (
                  <button
                    key={n}
                    role="radio"
                    aria-checked={given === n * 10}
                    aria-label={String(n)}
                    className={given !== null && n * 10 <= given ? "on" : ""}
                    onClick={() => setGiven(n * 10)}
                  >
                    ★
                  </button>
                ))}
              </div>
            </div>
          )}
          {decision === "no" && afterNo >= 1 && <p className="dim card-step">{t("agent.declined")}</p>}
        </div>
      )}
      {given !== null && afterRate >= 1 && (
        <p className="card-rating card-step">
          <span className="label">{t("card.rate.yours")}</span>{" "}
          <b>{t("card.rating.score", { score: (given / 10).toFixed(1) })}</b>
        </p>
      )}
    </>
  );
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
