import { Link } from "react-router-dom";
import type { Booking, Card } from "../api";
import { useI18n } from "../i18n";
import { metres, stay } from "../lib/format";
import { icsEvent } from "../lib/next";
import Icon from "./Icon";

// What the agent offers once the stay is booked. Every tile does one visible thing on the guest's side (a calendar
// file, a signed card, a map) and none of them books or pays, so the only consent on the page stays the Approve.

const STATION = "basel sbb";

function downloadIcs(booking: Booking, address?: string) {
  const url = URL.createObjectURL(new Blob([icsEvent(booking, address, new Date())], { type: "text/calendar" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = `${booking.booking_id}.ics`;
  a.click();
  URL.revokeObjectURL(url);
}

export default function NextSteps({
  booking,
  hotel,
  nearby,
}: {
  booking: Booking;
  /** The booked business's signed card, for its address and distances. */
  hotel?: Card | null;
  nearby?: { card: Card; shared?: string } | null;
}) {
  const { t, intl } = useI18n();
  const walk = hotel?.distances_m?.[STATION];
  const route = hotel?.address
    ? `https://www.openstreetmap.org/directions?engine=fossgis_osrm_foot&from=${encodeURIComponent("Basel SBB")}&to=${encodeURIComponent(hotel.address)}`
    : null;

  return (
    <div className="next-steps">
      <p>{t("next.intro")}</p>
      <ul>
        <li style={{ animationDelay: "0.1s" }}>
          <Icon name="calendar" />
          <div>
            <b>{t("next.calendar.title")}</b>
            <span>{t("next.calendar.body", { dates: stay(booking.check_in, booking.check_out, intl) })}</span>
          </div>
          <button className="quiet" onClick={() => downloadIcs(booking, hotel?.address)}>
            {t("next.calendar.cta")}
          </button>
        </li>
        {nearby && (
          <li style={{ animationDelay: "0.25s" }}>
            <Icon name="hive" />
            <div>
              <span className="label">
                {nearby.shared ? t("next.coffee.because", { feature: nearby.shared }) : t("next.coffee.nearby")}
              </span>
              <b>{nearby.card.name}</b>
              <span>
                {nearby.card.tagline}
                {nearby.card.policies?.reservations ? `. ${nearby.card.policies.reservations}.` : ""}
              </span>
            </div>
            <Link className="quiet" to={`/card/${nearby.card.slug}`}>
              {t("next.coffee.cta")}
            </Link>
          </li>
        )}
        {route && (
          <li style={{ animationDelay: "0.4s" }}>
            <Icon name="arrow" />
            <div>
              <b>{t("next.route.title")}</b>
              <span>
                {t("next.route.body", {
                  name: booking.business,
                  distance: walk !== undefined ? metres(walk, intl) : "–",
                })}
              </span>
            </div>
            <a className="quiet" href={route} target="_blank" rel="noopener noreferrer">
              {t("next.route.cta")}
            </a>
          </li>
        )}
      </ul>
      <p className="fine">{t("next.fine")}</p>
    </div>
  );
}
