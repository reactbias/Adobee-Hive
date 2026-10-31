import { useCallback, useEffect, useState } from "react";
import { ApiError, api, type AdminEntity } from "../api";
import { useI18n } from "../i18n";
import { dayOf } from "../lib/format";

// What this hub carries, for the operator who runs it. The overview counts the index; this is the list behind
// that count, and it comes from the same call, so the two cannot disagree.
//
// A 401 or 403 means the session is gone: the panel says so by handing control back to the sign-in form rather
// than showing an empty table, because an empty table and a lost session look identical and mean opposite things.

const lost = (e: unknown) => e instanceof ApiError && (e.status === 401 || e.status === 403);

/** Claimed or unclaimed, as a dot and a word: an unclaimed card is a lead, never a business that agreed. */
function Claimed({ claimed }: { claimed: boolean }) {
  const { t } = useI18n();
  return (
    <span className={claimed ? "status ok" : "status"}>
      {t(claimed ? "admin.entities.claimed" : "admin.entities.unclaimed")}
    </span>
  );
}

/** The entity list: id, name, kind, claimed, rating and count, and when the current version was published. */
export default function EntitiesPanel({ onLost }: { onLost?: () => void }) {
  const { t, intl } = useI18n();
  const [rows, setRows] = useState<AdminEntity[] | null>(null);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api
      .adminEntities()
      .then((out) => setRows(out.entities))
      .catch((e) => {
        if (lost(e) && onLost) onLost();
        else setError((e as Error).message);
        setRows([]);
      });
  }, [onLost]);
  useEffect(load, [load]);

  if (rows === null) return <p className="muted">{t("admin.loading")}</p>;
  return (
    <div className="stack loose">
      <p className="muted small">{t("admin.entities.lead")}</p>
      {error && <p className="error">{error}</p>}
      {!rows.length ? (
        <p className="muted">{t("admin.entities.empty")}</p>
      ) : (
        <>
          <p className="eyebrow">{t("admin.entities.count", { n: rows.length })}</p>
          <ul className="rows">
            {rows.map((e) => (
              <li key={e.id}>
                <span className="stack tight">
                  <strong>{e.name}</strong>
                  <span className="muted small">{t("admin.entities.who", { id: e.id, kind: e.kind })}</span>
                </span>
                <span className="stack tight">
                  <Claimed claimed={e.claimed} />
                  <span className="muted small">
                    {e.rating_count
                      ? t("admin.entities.rating", { rating: (e.rating ?? 0).toFixed(1), n: e.rating_count })
                      : t("admin.entities.noRating")}
                  </span>
                  <span className="muted small">
                    {t("admin.entities.published", { date: dayOf(e.published_at, intl) })}
                  </span>
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
