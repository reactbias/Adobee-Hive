import { useCallback, useEffect, useState } from "react";
import { ApiError, api, type AdminContactRow, type AdminEntity, type AdminEntityDetail, type AdminSide } from "../api";
import { useI18n } from "../i18n";
import type { Key } from "../i18n/en";
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

/** What an entity offers, or what it needs: the two sides the hub's index is actually made of. */
function Side({ heading, items }: { heading: Key; items: AdminSide[] }) {
  const { t } = useI18n();
  return (
    <section className="stack tight">
      <p className="eyebrow">{t(heading)}</p>
      {!items.length ? (
        <p className="muted small">{t("admin.entity.none")}</p>
      ) : (
        <ul className="rows tight">
          {items.map((item, i) => (
            <li key={`${item.title ?? i}`}>
              <span className="stack tight">
                <strong>{String(item.title ?? item.id ?? "")}</strong>
                {item.summary ? <span className="muted small">{String(item.summary)}</span> : null}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** Every published channel with the flag that actually applies to it, stricter of the two always winning. */
function Contact({ rows, fallback }: { rows: AdminContactRow[]; fallback: string }) {
  const { t } = useI18n();
  const shown = rows.filter((r) => r.value);
  return (
    <section className="stack tight">
      <p className="eyebrow">{t("admin.entity.contact")}</p>
      <p className="muted small">{t("admin.entity.sharingDefault", { flag: t(`admin.sharing.${fallback}` as Key) })}</p>
      {!shown.length ? (
        <p className="muted small">{t("admin.entity.contactNone")}</p>
      ) : (
        <ul className="rows tight">
          {shown.map((r) => (
            <li key={r.channel}>
              <span className="stack tight">
                <strong>{r.value}</strong>
                <span className="muted small">{r.channel}</span>
              </span>
              <span className={r.searchable ? "status ok" : "status"}>{t(`admin.sharing.${r.sharing}` as Key)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** One entity in full. Everything an operator needs to decide what to do about it, in one screen. */
function Detail({ id, onBack, onLost }: { id: string; onBack: () => void; onLost?: () => void }) {
  const { t, intl } = useI18n();
  const [out, setOut] = useState<AdminEntityDetail | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .adminEntity(id)
      .then(setOut)
      .catch((e) => {
        if (lost(e) && onLost) onLost();
        else setError((e as Error).message);
      });
  }, [id, onLost]);

  if (error) return <p className="error">{error}</p>;
  if (!out) return <p className="muted">{t("admin.loading")}</p>;
  const { entity, card, signature, trust } = out;
  return (
    <div className="stack loose">
      <button className="quiet self-start" onClick={onBack}>
        {t("admin.entity.back")}
      </button>
      <section className="admin-card stack tight">
        <h3>{entity.name}</h3>
        <p className="muted small">{t("admin.entities.who", { id: entity.id, kind: entity.kind })}</p>
        {card.tagline ? <p>{String(card.tagline)}</p> : null}
        {card.description ? <p className="muted small">{String(card.description)}</p> : null}
        <div className="statuses">
          <Claimed claimed={entity.claimed} />
          <span className={signature.valid ? "status ok" : "status no"}>
            {t(signature.valid ? "trust.signed" : "trust.invalid")}
          </span>
          <span className={out.blocked ? "status no" : "status"}>
            {out.blocked ? t("admin.entity.isBlocked") : t("admin.entity.notBlocked")}
          </span>
        </div>
        {out.blocked && out.block ? (
          <p className="muted small">{t("admin.entity.blockedWhy", { reason: out.block.reason })}</p>
        ) : null}
      </section>

      <Side heading="admin.entity.offers" items={out.offers} />
      <Side heading="admin.entity.needs" items={out.needs} />
      <Contact rows={out.contact} fallback={out.sharing_default} />

      <section className="stack tight">
        <p className="eyebrow">{t("admin.entity.trust")}</p>
        <p className="muted small">
          {entity.rating_count
            ? t("admin.entities.rating", { rating: (entity.rating ?? 0).toFixed(1), n: entity.rating_count })
            : t("admin.entities.noRating")}
        </p>
        <p className="muted small">{t("admin.entity.attestations", { n: trust.attestations.length })}</p>
      </section>

      <section className="stack tight">
        <p className="eyebrow">{t("admin.entity.signature")}</p>
        <p className="muted small">{t("admin.entity.version", { n: signature.version ?? 0 })}</p>
        <p className="muted small">{signature.algorithm}</p>
        <p className="mono small key-line">{signature.public_key}</p>
        <span className={signature.fresh ? "status ok" : "status no"}>
          {signature.fresh
            ? t("admin.entity.validUntil", { date: dayOf(signature.valid_until, intl) })
            : t("admin.entity.stale")}
        </span>
      </section>
    </div>
  );
}

/** The entity list: id, name, kind, claimed, rating and count, and when the current version was published. */
export default function EntitiesPanel({ onLost }: { onLost?: () => void }) {
  const { t, intl } = useI18n();
  const [rows, setRows] = useState<AdminEntity[] | null>(null);
  const [open, setOpen] = useState("");
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

  if (open) return <Detail id={open} onBack={() => setOpen("")} onLost={onLost} />;
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
                <button className="quiet" onClick={() => setOpen(e.id)}>
                  {t("admin.entity.open")}
                </button>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
