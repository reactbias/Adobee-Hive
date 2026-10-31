import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, mcpUrl, type Card } from "../api";
import Display from "../components/Display";
import Icon, { type IconName } from "../components/Icon";
import TrustBadge from "../components/TrustBadge";
import { useI18n } from "../i18n";
import type { Key } from "../i18n/en";
import { capitalise, chf } from "../lib/format";

const PRINCIPLES: [IconName, Key, Key][] = [
  ["seal", "home.p1.title", "home.p1.body"],
  ["rank", "home.p2.title", "home.p2.body"],
  ["receipt", "home.p3.title", "home.p3.body"],
  ["yes", "home.p4.title", "home.p4.body"],
];
const REFUSALS: [IconName, Key, Key][] = [
  ["coin", "home.no1.title", "home.no1.body"],
  ["eyeOff", "home.no2.title", "home.no2.body"],
  ["quote", "home.no3.title", "home.no3.body"],
];

const fromPrice = (c: Card) => (c.units.length ? Math.min(...c.units.map((u) => u.price_chf)) : null);

// A real card from the Hive, set like a specimen: the product is the card.
function Specimen({ card }: { card: Card }) {
  const { t, intl } = useI18n();
  const price = fromPrice(card);
  return (
    <figure className="specimen">
      <div className="specimen-card">
        <div className="spread">
          <span className="eyebrow">{capitalise(card.kind)}</span>
          <span className="mono muted">v{card.version}</span>
        </div>
        <h3>{card.name}</h3>
        <p className="muted">{card.tagline}</p>
        <p className="specimen-features">{card.features.slice(0, 5).join(" · ")}</p>
        {price !== null && <p className="specimen-price">{t("home.from", { price: chf(price, intl) })}</p>}
        <div className="specimen-seal">
          <TrustBadge trust={card.trust} compact />
          <code>Ed25519 · {card.trust.signature.slice(0, 22)}…</code>
        </div>
      </div>
      <figcaption className="muted">{t("home.specimen")}</figcaption>
    </figure>
  );
}

export default function Home() {
  const { t } = useI18n();
  const [cards, setCards] = useState<Card[]>([]);
  useEffect(() => {
    api
      .cards()
      .then((all) => setCards(all.filter((c) => c.trust.claimed !== false))) // unclaimed examples live on /ask
      .catch(() => setCards([]));
  }, []);
  const featured = cards.find((c) => c.slug === "rheinblick") ?? cards[0];

  return (
    <>
      <section className="hero">
        <div className="hero-inner">
          <div className="hero-copy">
            <span className="eyebrow">{t("home.eyebrow")}</span>
            <h1>
              <Display text={t("home.title")} />
            </h1>
            <p className="lead">{t("home.lead")}</p>
            <div className="row hero-actions">
              <Link className="btn light" to="/agent">
                {t("home.cta.agent")}
              </Link>
              <Link className="btn quiet arrow" to="/owner">
                {t("home.cta.owner")}
              </Link>
            </div>
          </div>
          {featured && <Specimen card={featured} />}
        </div>
        <dl className="hero-facts">
          <div>
            <dt>{t("home.fact.cards")}</dt>
            <dd className="num">{cards.length || "–"}</dd>
          </div>
          <div>
            <dt>{t("home.fact.signature")}</dt>
            <dd>Ed25519</dd>
          </div>
          <div>
            <dt>{t("home.fact.protocol")}</dt>
            <dd>MCP</dd>
          </div>
          <div>
            <dt>{t("home.fact.placement")}</dt>
            <dd className="num">0</dd>
          </div>
        </dl>
      </section>

      <section className="section">
        <div className="section-head">
          <span className="eyebrow">{t("home.principles.eyebrow")}</span>
          <h2>
            <Display text={t("home.principles.title")} />
          </h2>
        </div>
        <ol className="principles">
          {PRINCIPLES.map(([icon, title, body], n) => (
            <li key={title}>
              <div className="principle-head">
                <Icon name={icon} size={28} />
                <span className="num principle-n">{String(n + 1).padStart(2, "0")}</span>
              </div>
              <h3>{t(title)}</h3>
              <p>{t(body)}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="section band">
        <span className="eyebrow">{t("home.twist.eyebrow")}</span>
        <h2>
          <Display text={t("home.twist.title")} />
        </h2>
        <p className="lead">{t("home.twist.body")}</p>
        <Link className="btn quiet arrow" to="/demand">
          {t("home.twist.cta")}
        </Link>
      </section>

      <section className="section">
        <div className="section-head">
          <span className="eyebrow">{t("home.hive.eyebrow")}</span>
          <h2>
            <Display text={t("home.hive.title")} />
          </h2>
          <p className="lead">
            {t("home.hive.body")} <code className="inline-code">{mcpUrl()}</code>
          </p>
        </div>
        <ul className="rows directory">
          {cards.map((c) => (
            <li key={c.id}>
              <Link to={`/card/${c.slug}`} className="directory-row">
                <span className="directory-kind">{capitalise(c.kind)}</span>
                <span className="directory-name">{c.name}</span>
                <span className="directory-tagline">{c.tagline}</span>
                <TrustBadge trust={c.trust} compact />
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <section className="section">
        <div className="section-head">
          <span className="eyebrow">{t("home.no.eyebrow")}</span>
          <h2>
            <Display text={t("home.no.title")} />
          </h2>
        </div>
        <ul className="refusals">
          {REFUSALS.map(([icon, title, body]) => (
            <li key={title}>
              <Icon name={icon} size={28} />
              <h3>{t(title)}</h3>
              <p>{t(body)}</p>
            </li>
          ))}
        </ul>
      </section>

      <section className="section closing">
        <p>{t("home.closing")}</p>
      </section>
    </>
  );
}
