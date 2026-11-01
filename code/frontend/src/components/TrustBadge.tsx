import type { Trust } from "../api";
import { useI18n } from "../i18n";

// How much a card can be trusted, as quiet status lines: signature, attested claims, reviews from verified bookings.
export default function TrustBadge({ trust, compact = false }: { trust: Trust; compact?: boolean }) {
  const { t } = useI18n();
  const reviews = trust.verified_reviews;
  return (
    <div className="statuses">
      <span className={`status ${!trust.signature_valid ? "no" : trust.claimed === false ? "warm" : "ok"}`}>
        {!trust.signature_valid
          ? t("trust.invalid")
          : trust.claimed === false
            ? t("trust.unclaimed")
            : t("trust.signed")}
      </span>
      {!compact &&
        trust.attestations.map((a) => (
          <span key={a.claim + a.attested_by} className="status ok" title={a.attested_by}>
            {t("trust.attested", { claim: a.claim })}
          </span>
        ))}
      {trust.claimed !== false && (
        <span className="status">
          {reviews.count
            ? t("trust.reviews", { avg: String(reviews.average), n: reviews.count })
            : t("trust.noReviews")}
        </span>
      )}
    </div>
  );
}
