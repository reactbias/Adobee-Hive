import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, type Booking, type Card, type FreeUnit } from "../api";
import TrustBadge from "../components/TrustBadge";
import { useI18n } from "../i18n";
import { capitalise, chf, day } from "../lib/format";

const label = (k: string) => capitalise(k.replace(/_/g, " "));

// The human fallback: the same signed card, rendered as a page. No second CMS.
export default function CardPage() {
  const { t, intl } = useI18n();
  const { slug = "" } = useParams();
  const [card, setCard] = useState<Card | null>(null);
  const [dates, setDates] = useState({ check_in: "2026-11-13", check_out: "2026-11-15", guests: 1, name: "" });
  const [units, setUnits] = useState<FreeUnit[] | null>(null);
  const [booking, setBooking] = useState<Booking | null>(null);
  const [error, setError] = useState("");
  const [tamper, setTamper] = useState<{ original: boolean; tampered: boolean } | null>(null);

  useEffect(() => {
    api
      .card(slug)
      .then(setCard)
      .catch((e) => setError(e.message));
  }, [slug]);

  async function check() {
    if (!card) return;
    setError("");
    try {
      setUnits((await api.availability(card.id, dates.check_in, dates.check_out, dates.guests)).available_units);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function book(unit: FreeUnit) {
    if (!card) return;
    try {
      setBooking(
        await api.bookAsHuman(card.id, {
          unit_id: unit.id,
          check_in: dates.check_in,
          check_out: dates.check_out,
          guest_name: dates.name || t("card.walkIn"),
          guests: dates.guests,
        }),
      );
    } catch (e) {
      setError((e as Error).message);
    }
  }

  // What an agent does with every card it reads: re-check the owner's signature.
  async function tamperTest() {
    if (!card) return;
    const forged: Card = JSON.parse(JSON.stringify(card));
    if (forged.units.length) forged.units[0].price_chf = 1;
    else forged.features = [...forged.features, "free breakfast"];
    const [original, tampered] = await Promise.all([api.verify(card), api.verify(forged)]);
    setTamper({ original: original.signature_valid, tampered: tampered.signature_valid });
  }

  if (!card) return <p className={error ? "error" : "muted"}>{error || t("card.loading")}</p>;
  return (
    <div className="stack loose">
      <header className="page-head">
        <span className="eyebrow">{capitalise(card.kind)}</span>
        <h1>{card.name}</h1>
        <p className="lead">{card.tagline}</p>
        <TrustBadge trust={card.trust} />
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

        {card.units.length > 0 && (
          <section className="panel lifted stack">
            <h3>{t("card.book.title")}</h3>
            <div className="row nowrap-row">
              <div className="field">
                <label htmlFor="in">{t("card.in")}</label>
                <input
                  id="in"
                  type="date"
                  value={dates.check_in}
                  onChange={(e) => setDates({ ...dates, check_in: e.target.value })}
                />
              </div>
              <div className="field">
                <label htmlFor="out">{t("card.out")}</label>
                <input
                  id="out"
                  type="date"
                  value={dates.check_out}
                  onChange={(e) => setDates({ ...dates, check_out: e.target.value })}
                />
              </div>
              <div className="field narrow">
                <label htmlFor="guests">{t("card.guests")}</label>
                <input
                  id="guests"
                  type="number"
                  min={1}
                  value={dates.guests}
                  onChange={(e) => setDates({ ...dates, guests: Number(e.target.value) })}
                />
              </div>
            </div>
            <div>
              <label htmlFor="name">{t("card.name")}</label>
              <input id="name" value={dates.name} onChange={(e) => setDates({ ...dates, name: e.target.value })} />
            </div>
            <button className="ghost" onClick={check}>
              {t("card.check")}
            </button>
            {units?.length === 0 && <p className="muted">{t("card.full")}</p>}
            {units && units.length > 0 && (
              <ul className="rows compact">
                {units.map((u) => (
                  <li key={u.id} className="spread unit-row">
                    <span>
                      {u.name}
                      <span className="muted block">
                        {t("trace.perNight", { price: chf(u.price_chf, intl) })} ·{" "}
                        {t("trace.left", { n: String(u.left) })}
                      </span>
                    </span>
                    <button onClick={() => book(u)}>{t("card.bookFor", { price: chf(u.total_chf, intl) })}</button>
                  </li>
                ))}
              </ul>
            )}
            {booking && (
              <p className="status ok">{t("card.booked", { unit: booking.unit_name, id: booking.booking_id })}</p>
            )}
            {error && <p className="error">{error}</p>}
          </section>
        )}
      </div>

      <section className="section tamper">
        <div className="section-head">
          <span className="eyebrow">{t("card.tamper.eyebrow")}</span>
          <h2>{t("card.tamper.title")}</h2>
          <p className="lead">{t("card.tamper.body")}</p>
        </div>
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
          </dl>
        )}
      </section>

      <p className="muted">
        {t("card.footer", { version: card.version, date: day(card.published_at.slice(0, 10), intl) })}
      </p>
    </div>
  );
}
