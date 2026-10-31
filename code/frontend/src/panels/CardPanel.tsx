import { useEffect, useState } from "react";
import { api, mcpUrl, type Card } from "../api";
import TrustBadge from "../components/TrustBadge";
import { useI18n } from "../i18n";
import { capitalise, day } from "../lib/format";

const label = (k: string) => capitalise(k.replace(/_/g, " "));

// The signed card the agent read, rendered for people, with the tamper test. No second CMS: it is the same data.
export default function CardPanel({ slug, onSlug }: { slug: string; onSlug: (slug: string) => void }) {
  const { t, intl } = useI18n();
  const [cards, setCards] = useState<Card[]>([]);
  const [card, setCard] = useState<Card | null>(null);
  const [error, setError] = useState("");
  const [tamper, setTamper] = useState<{ original: boolean; tampered: boolean; stranger: boolean } | null>(null);

  useEffect(() => {
    api
      .cards()
      .then((all) => setCards(all.filter((c) => c.trust.claimed !== false))) // unclaimed examples live under Ask
      .catch(() => setCards([]));
  }, []);
  useEffect(() => {
    setTamper(null);
    setError("");
    api
      .card(slug)
      .then(setCard)
      .catch((e) => setError(e.message));
  }, [slug]);

  // What an agent does with every card it reads: re-check the owner's signature.
  async function tamperTest() {
    if (!card) return;
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
    setTamper({
      original: original.signature_valid,
      tampered: tampered.signature_valid,
      stranger: stranger.signature_valid,
    });
  }

  const picker = (
    <div className="picker">
      <label htmlFor="door-card">{t("door.card.pick")}</label>
      <select id="door-card" value={card?.slug ?? slug} onChange={(e) => onSlug(e.target.value)}>
        {!cards.some((c) => c.slug === (card?.slug ?? slug)) && card && <option value={card.slug}>{card.name}</option>}
        {cards.map((c) => (
          <option key={c.id} value={c.slug}>
            {c.name}
          </option>
        ))}
      </select>
    </div>
  );

  if (!card)
    return (
      <div className="stack">
        {cards.length > 0 && picker}
        <p className={error ? "error" : "muted"}>{error || t("card.loading")}</p>
      </div>
    );
  return (
    <div className="stack loose">
      <header className="panel-head">
        <div className="stack">
          <span className="eyebrow">{capitalise(card.kind)}</span>
          <h3>{card.name}</h3>
          <p className="lead">{card.tagline}</p>
          <TrustBadge trust={card.trust} />
        </div>
        {picker}
      </header>

      <div className="grid split">
        <section className="stack loose">
          {card.description && <p className="prose">{card.description}</p>}
          <p className="meta features">
            {card.features.map((f) => (
              <span key={f}>{f}</span>
            ))}
          </p>
          <dl className="facts">
            {card.address && (
              <div>
                <dt>{t("card.address")}</dt>
                <dd>{card.address}</dd>
              </div>
            )}
            {card.contact &&
              Object.entries(card.contact).map(([k, v]) => (
                <div key={k}>
                  <dt>{label(k)}</dt>
                  <dd>{v}</dd>
                </div>
              ))}
          </dl>
          {(card.policies || card.opening_hours) && (
            <table>
              <tbody>
                {Object.entries({ ...card.policies, ...card.opening_hours }).map(([k, v]) => (
                  <tr key={k}>
                    <th>{label(k)}</th>
                    <td>{v}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {card.trust.verified_reviews.recent.length > 0 && (
            <ul className="rows compact">
              {card.trust.verified_reviews.recent.map((r, i) => (
                <li key={i}>
                  <span className="stars-static" aria-label={`${r.rating} / 5`}>
                    {"★".repeat(r.rating)}
                  </span>{" "}
                  {r.text}
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="panel stack tamper">
          <span className="eyebrow">{t("card.tamper.eyebrow")}</span>
          <h3>{t("card.tamper.title")}</h3>
          <p className="muted">{t("card.tamper.body")}</p>
          <button className="ghost self-start" onClick={tamperTest}>
            {card.units.length ? t("card.tamper.price") : t("card.tamper.perk")}
          </button>
          {tamper && (
            <dl className="verdicts reveal">
              <div className={tamper.original ? "ok" : "no"}>
                <dt>{t("card.tamper.original")}</dt>
                <dd>{tamper.original ? t("card.tamper.valid") : t("card.tamper.invalid")}</dd>
              </div>
              <div className={tamper.tampered ? "ok" : "no"}>
                <dt>{t("card.tamper.forged")}</dt>
                <dd>{tamper.tampered ? t("card.tamper.valid") : t("card.tamper.rejected")}</dd>
              </div>
              <div className={tamper.stranger ? "ok" : "no"}>
                <dt>{t("card.tamper.stranger")}</dt>
                <dd>{tamper.stranger ? t("card.tamper.valid") : t("card.tamper.rejected")}</dd>
              </div>
            </dl>
          )}
        </section>
      </div>

      <p className="muted small">
        {t("card.footer", { version: card.version, date: day(card.published_at.slice(0, 10), intl) })}{" "}
        <code className="inline-code">{mcpUrl()}</code>
      </p>
    </div>
  );
}
