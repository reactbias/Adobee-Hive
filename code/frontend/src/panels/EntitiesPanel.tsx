import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  api,
  type AdminContactRow,
  type AdminEntity,
  type AdminEntityDetail,
  type AdminSide,
  type AuditEntry,
} from "../api";
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

// A destructive control says what it will do before it does it, and names the thing. Three acts are offered from
// the entity view and they are not the same act, which is exactly why they are spelled out:
//
//   remove   this hub stops carrying it. Out of search, not bookable. Every signed version is kept.
//   restore  carry it again.
//   block    refuse it wherever it comes from, including over a peer hub that relays it.
//
// An operator will reach for the wrong one unless the screen says which is which, so the screen says it.

type Act = "" | "remove" | "restore" | "block";

const WORDS: Record<Exclude<Act, "">, { title: Key; will: Key; note: Key; go: Key }> = {
  remove: {
    title: "admin.remove.confirm",
    will: "admin.remove.will",
    note: "admin.remove.notBlock",
    go: "admin.remove.do",
  },
  restore: {
    title: "admin.restore.confirm",
    will: "admin.restore.will",
    note: "admin.restore.note",
    go: "admin.restore.do",
  },
  block: {
    title: "admin.block.confirm",
    will: "admin.block.will",
    note: "admin.block.notRemove",
    go: "admin.block.do",
  },
};

/** The one step between a click and an act: what will happen, to what, and a reason that is not optional. */
function Confirm({
  act,
  name,
  busy,
  onCancel,
  onGo,
}: {
  act: Exclude<Act, "">;
  name: string;
  busy: boolean;
  onCancel: () => void;
  onGo: (reason: string) => void;
}) {
  const { t } = useI18n();
  const [reason, setReason] = useState("");
  const words = WORDS[act];
  const ready = reason.trim().length > 0;
  return (
    <section className="admin-card stack tight">
      <h3>{t(words.title, { name })}</h3>
      <p>{t(words.will)}</p>
      <p className="muted small">{t(words.note)}</p>
      <label htmlFor="act-reason">{t("admin.remove.reason")}</label>
      <input id="act-reason" value={reason} onChange={(e) => setReason(e.target.value)} />
      <div className="row">
        <button onClick={() => onGo(reason.trim())} disabled={busy || !ready}>
          {t(words.go)}
        </button>
        <button className="quiet" onClick={onCancel} disabled={busy}>
          {t("admin.remove.cancel")}
        </button>
      </div>
      {!ready && <p className="muted small">{t("admin.remove.reasonNeeded")}</p>}
    </section>
  );
}

/** What was changed here, when, why, and with which credential. Never a person: the hub cannot tell. */
function Ledger({ rows }: { rows: AuditEntry[] }) {
  const { t, intl } = useI18n();
  return (
    <section className="stack tight">
      <p className="eyebrow">{t("admin.ledger")}</p>
      {!rows.length ? (
        <p className="muted small">{t("admin.ledger.empty")}</p>
      ) : (
        <ul className="rows tight">
          {rows.map((r) => (
            <li key={r.id}>
              <span className="stack tight">
                <strong>{r.reason}</strong>
                {/* The action is a code, not prose: set in mono like every other identifier (BRAND.md). */}
                <span className="mono small">{r.action}</span>
                <span className="muted small">
                  {t("admin.ledger.who", {
                    credential: t(
                      r.credential === "static token" ? "admin.credential.token" : "admin.credential.session",
                    ),
                    date: dayOf(r.at, intl),
                  })}
                </span>
              </span>
            </li>
          ))}
        </ul>
      )}
      <p className="muted small">{t("admin.ledger.whoLimit")}</p>
    </section>
  );
}

/** One entity in full. Everything an operator needs to decide what to do about it, in one screen. */
function Detail({ id, onBack, onLost }: { id: string; onBack: () => void; onLost?: () => void }) {
  const { t, intl } = useI18n();
  const [out, setOut] = useState<AdminEntityDetail | null>(null);
  const [ledger, setLedger] = useState<AuditEntry[]>([]);
  const [act, setAct] = useState<Act>("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api
      .adminEntity(id)
      .then(setOut)
      .catch((e) => {
        if (lost(e) && onLost) onLost();
        else setError((e as Error).message);
      });
    api
      .adminAudit(id)
      .then((a) => setLedger(a.entries))
      .catch(() => setLedger([]));
  }, [id, onLost]);
  useEffect(load, [load]);

  async function run(reason: string) {
    if (!out) return;
    setBusy(true);
    setError("");
    try {
      if (act === "remove") await api.adminRemoveEntity(out.entity.id, reason);
      else if (act === "restore") await api.adminRestoreEntity(out.entity.id, reason);
      else if (act === "block") await api.adminBlock("entity", out.entity.id, reason);
      setAct("");
      load();
    } catch (e) {
      if (lost(e) && onLost) onLost();
      else setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (error && !out) return <p className="error">{error}</p>;
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
          <span className={out.carried ? "status ok" : "status no"}>
            {out.carried ? t("admin.remove.carried") : t("admin.remove.removed")}
          </span>
          <Claimed claimed={entity.claimed} />
          <span className={signature.valid ? "status ok" : "status no"}>
            {t(signature.valid ? "trust.signed" : "trust.invalid")}
          </span>
          <span className={out.blocked ? "status no" : "status"}>
            {out.blocked ? t("admin.entity.isBlocked") : t("admin.entity.notBlocked")}
          </span>
        </div>
        {!out.carried && out.removal ? (
          <p className="muted small">{t("admin.remove.why", { reason: out.removal.reason })}</p>
        ) : null}
        {out.blocked && out.block ? (
          <p className="muted small">{t("admin.entity.blockedWhy", { reason: out.block.reason })}</p>
        ) : null}
      </section>

      {error && <p className="error">{error}</p>}
      {act ? (
        <Confirm act={act} name={entity.name} busy={busy} onCancel={() => setAct("")} onGo={run} />
      ) : (
        <div className="row">
          {out.carried ? (
            <button className="quiet" onClick={() => setAct("remove")}>
              {t("admin.remove.button")}
            </button>
          ) : (
            <button className="quiet" onClick={() => setAct("restore")}>
              {t("admin.restore.button")}
            </button>
          )}
          {!out.blocked && (
            <button className="quiet" onClick={() => setAct("block")}>
              {t("admin.block.button")}
            </button>
          )}
        </div>
      )}

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

      <Ledger rows={ledger} />
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
          <p className="eyebrow">{t("admin.entities.count", { n: rows.filter((e) => e.carried).length })}</p>
          <ul className="rows">
            {rows.map((e) => (
              <li key={e.id}>
                <span className="stack tight">
                  <strong>{e.name}</strong>
                  <span className="muted small">{t("admin.entities.who", { id: e.id, kind: e.kind })}</span>
                </span>
                <span className="stack tight">
                  {!e.carried && <span className="status no">{t("admin.remove.removed")}</span>}
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
