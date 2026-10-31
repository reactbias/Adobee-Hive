import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, mcpUrl, type Card } from "../api";
import TrustBadge from "../components/TrustBadge";
import { useI18n } from "../i18n";
import type { Key } from "../i18n/en";
import { capitalise, chf } from "../lib/format";

const PRINCIPLES: [Key, Key][] = [
  ["home.p1.title", "home.p1.body"],
  ["home.p2.title", "home.p2.body"],
  ["home.p3.title", "home.p3.body"],
  ["home.p4.title", "home.p4.body"],
];
const REFUSALS: [Key, Key][] = [
  ["home.no1.title", "home.no1.body"],
  ["home.no2.title", "home.no2.body"],
  ["home.no3.title", "home.no3.body"],
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
      .then(setCards)
      .catch(() => setCards([]));
  }, []);
  const featured = cards.find((c) => c.slug === "rheinblick") ?? cards[0];

  return (
    <>
      <section className="hero">
        <div className="hero-copy">
          <span className="eyebrow">{t("home.eyebrow")}</span>
          <h1>{t("home.title")}</h1>
          <p className="lead">{t("home.lead")}</p>
          <div className="row hero-actions">
            <Link className="btn" to="/agent">
              {t("home.cta.agent")}
            </Link>
            <Link className="btn quiet arrow" to="/owner">
              {t("home.cta.owner")}
            </Link>
          </div>
        </div>
        {featured && <Specimen card={featured} />}
      </section>

      <section className="section">
        <div className="section-head">
          <span className="eyebrow">{t("home.principles.eyebrow")}</span>
          <h2>{t("home.principles.title")}</h2>
        </div>
        <ol className="principles">
          {PRINCIPLES.map(([title, body], n) => (
            <li key={title}>
              <span className="num principle-n">{String(n + 1).padStart(2, "0")}</span>
              <h3>{t(title)}</h3>
              <p>{t(body)}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="section band">
        <span className="eyebrow">{t("home.twist.eyebrow")}</span>
        <h2>{t("home.twist.title")}</h2>
        <p className="lead">{t("home.twist.body")}</p>
        <Link className="btn quiet arrow" to="/demand">
          {t("home.twist.cta")}
        </Link>
      </section>

      <section className="section">
        <div className="section-head">
          <span className="eyebrow">{t("home.hive.eyebrow")}</span>
          <h2>{t("home.hive.title")}</h2>
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
          <h2>{t("home.no.title")}</h2>
        </div>
        <ul className="refusals">
          {REFUSALS.map(([title, body]) => (
            <li key={title}>
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
