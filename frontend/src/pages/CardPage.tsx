import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, type Booking, type Card, type FreeUnit } from "../api";
import TrustBadge from "../components/TrustBadge";

// The human fallback: the same signed card, rendered as a page. No second CMS.
export default function CardPage() {
  const { slug = "" } = useParams();
  const [card, setCard] = useState<Card | null>(null);
  const [dates, setDates] = useState({ check_in: "2026-11-13", check_out: "2026-11-15", guests: 1, name: "" });
  const [units, setUnits] = useState<FreeUnit[] | null>(null);
  const [booking, setBooking] = useState<Booking | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.card(slug).then(setCard).catch((e) => setError(e.message));
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
      setBooking(await api.bookAsHuman(card.id, { unit_id: unit.id, check_in: dates.check_in, check_out: dates.check_out, guest_name: dates.name || "Walk-in guest", guests: dates.guests }));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  if (!card) return <p className={error ? "error" : "muted"}>{error || "Loading..."}</p>;
  return (
    <div className="stack">
      <span className="chip">{card.kind}</span>
      <h1>{card.name}</h1>
      <p className="lead">{card.tagline}</p>
      <TrustBadge trust={card.trust} />
      <div className="grid two">
        <section className="panel stack">
          <p>{card.description}</p>
          <div>{card.features.map((f) => <span key={f} className="chip">{f}</span>)}</div>
          {card.address && <div><strong>Address:</strong> {card.address}</div>}
          {card.contact && <div><strong>Contact:</strong> {Object.values(card.contact).join(" · ")}</div>}
          {card.policies && (
            <table><tbody>
              {Object.entries(card.policies).map(([k, v]) => <tr key={k}><th>{k.replace("_", " ")}</th><td>{v}</td></tr>)}
            </tbody></table>
          )}
          {card.opening_hours && (
            <table><tbody>
              {Object.entries(card.opening_hours).map(([k, v]) => <tr key={k}><th>{k}</th><td>{v}</td></tr>)}
            </tbody></table>
          )}
          {card.trust.verified_reviews.recent.map((r, i) => (
            <div key={i} className="muted">{"★".repeat(r.rating)} {r.text}</div>
          ))}
        </section>
        {card.units.length > 0 && (
          <section className="panel stack">
            <h3>Book directly</h3>
            <div className="row">
              <div style={{ flex: 1 }}><label>Check in</label><input type="date" value={dates.check_in} onChange={(e) => setDates({ ...dates, check_in: e.target.value })} /></div>
              <div style={{ flex: 1 }}><label>Check out</label><input type="date" value={dates.check_out} onChange={(e) => setDates({ ...dates, check_out: e.target.value })} /></div>
              <div style={{ width: 90 }}><label>Guests</label><input type="number" min={1} value={dates.guests} onChange={(e) => setDates({ ...dates, guests: Number(e.target.value) })} /></div>
            </div>
            <div><label>Your name</label><input value={dates.name} onChange={(e) => setDates({ ...dates, name: e.target.value })} /></div>
            <button onClick={check}>Check availability</button>
            {units?.length === 0 && <p className="muted">Fully booked for these dates.</p>}
            {units?.map((u) => (
              <div key={u.id} className="row" style={{ justifyContent: "space-between" }}>
                <span>{u.name} · CHF {u.price_chf}/night · {u.left} left</span>
                <button onClick={() => book(u)}>Book CHF {u.total_chf}</button>
              </div>
            ))}
            {booking && <p><strong>Booked.</strong> {booking.unit_name}, reference {booking.booking_id}.</p>}
            {error && <p className="error">{error}</p>}
          </section>
        )}
      </div>
      <p className="muted">Card version {card.version}, published {card.published_at}. Agents read the same data at the Hive's MCP endpoint.</p>
    </div>
  );
}
