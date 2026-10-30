import type { Trust } from "../api";

export default function TrustBadge({ trust }: { trust: Trust }) {
  const reviews = trust.verified_reviews;
  return (
    <div>
      <span className={`chip ${trust.signature_valid ? "ok" : "no"}`}>
        {trust.signature_valid ? "Signed by owner" : "Signature invalid"}
      </span>
      {trust.attestations.map((a) => (
        <span key={a.claim + a.attested_by} className="chip ok" title={a.attested_by}>
          {a.claim} verified
        </span>
      ))}
      <span className="chip">
        {reviews.count ? `${reviews.average} / 5 from ${reviews.count} verified stays` : "No verified stays yet"}
      </span>
    </div>
  );
}
