import { useCallback, useEffect, useState } from "react";
import { ApiError, api, type AdminPeer } from "../api";
import Calibration from "../components/Calibration";
import { useI18n } from "../i18n";
import { dayOf } from "../lib/format";

// The connected hubs, as something an operator can change rather than read. Peers used to be HIVE_PEER_URLS and
// nothing else, so adding a neighbour meant editing a deployment and restarting; now the list is stored and the
// next federated search obeys it.
//
// Two rules shape this screen:
//
//   Nothing here fetches from a peer. Whether a peer answers is the stored result of the last Check now, so one
//   dead neighbour cannot make the page slow or blank. It reads as "no answer" with the time it was last tried.
//
//   Removing is not blocking, and both are offered, so the difference is written on the screen. Removing stops
//   this hub asking a peer. Blocking refuses it in both directions and drops cards that travelled through it.

const lost = (e: unknown) => e instanceof ApiError && (e.status === 401 || e.status === 403);

/** Whether a peer answered the last time anyone asked. Unasked is not the same as silent. */
function Answers({ peer }: { peer: AdminPeer }) {
  const { t, intl } = useI18n();
  const word = peer.answers === null ? "unasked" : peer.answers ? "answers" : "silent";
  return (
    <span className="stack tight">
      <span className={`status ${peer.answers === null ? "" : peer.answers ? "ok" : "no"}`}>
        {t(`admin.peers.${word}`)}
      </span>
      {peer.last_checked_at && (
        <span className="muted small">{t("admin.peers.lastChecked", { date: dayOf(peer.last_checked_at, intl) })}</span>
      )}
      {peer.answers === false && peer.last_error && <span className="muted small">{peer.last_error}</span>}
    </span>
  );
}

/** The one step between a click and a change: what it will do, to which hub, and a reason that is required. */
function Ask({
  what,
  name,
  busy,
  onCancel,
  onGo,
}: {
  what: "remove" | "block";
  name: string;
  busy: boolean;
  onCancel: () => void;
  onGo: (reason: string) => void;
}) {
  const { t } = useI18n();
  const [reason, setReason] = useState("");
  const ready = reason.trim().length > 0;
  return (
    <section className="admin-card stack tight">
      <h3>{t(what === "remove" ? "admin.peers.removeConfirm" : "admin.peers.blockConfirm", { name })}</h3>
      <p>{t(what === "remove" ? "admin.peers.removeWill" : "admin.peers.blockWill")}</p>
      <p className="muted small">
        {t(what === "remove" ? "admin.peers.removeNotBlock" : "admin.peers.blockNotRemove")}
      </p>
      <label htmlFor="peer-act-reason">{t("admin.peers.reason")}</label>
      <input id="peer-act-reason" value={reason} onChange={(e) => setReason(e.target.value)} />
      <div className="row">
        <button onClick={() => onGo(reason.trim())} disabled={busy || !ready}>
          {t(what === "remove" ? "admin.peers.removeDo" : "admin.peers.blockDo")}
        </button>
        <button className="quiet" onClick={onCancel} disabled={busy}>
          {t("admin.peers.cancel")}
        </button>
      </div>
      {!ready && <p className="muted small">{t("admin.peers.reasonNeeded")}</p>}
    </section>
  );
}

/** Rename a peer, or record the hub id it turned out to have. Only the fields filled in are changed. */
function Edit({
  peer,
  busy,
  onCancel,
  onGo,
}: {
  peer: AdminPeer;
  busy: boolean;
  onCancel: () => void;
  onGo: (name: string, hubId: string, reason: string) => void;
}) {
  const { t } = useI18n();
  const [name, setName] = useState(peer.name);
  const [hubId, setHubId] = useState(peer.hub_id);
  const [reason, setReason] = useState("");
  const ready = reason.trim().length > 0;
  return (
    <section className="admin-card stack tight">
      <h3>{peer.url}</h3>
      <label htmlFor="peer-name">{t("admin.peers.name")}</label>
      <input id="peer-name" value={name} onChange={(e) => setName(e.target.value)} />
      <label htmlFor="peer-hub">{t("admin.peers.hubId")}</label>
      <input id="peer-hub" value={hubId} onChange={(e) => setHubId(e.target.value)} />
      <label htmlFor="peer-edit-reason">{t("admin.peers.reason")}</label>
      <input id="peer-edit-reason" value={reason} onChange={(e) => setReason(e.target.value)} />
      <div className="row">
        <button onClick={() => onGo(name.trim(), hubId.trim(), reason.trim())} disabled={busy || !ready}>
          {t("admin.peers.save")}
        </button>
        <button className="quiet" onClick={onCancel} disabled={busy}>
          {t("admin.peers.cancel")}
        </button>
      </div>
      {!ready && <p className="muted small">{t("admin.peers.reasonNeeded")}</p>}
    </section>
  );
}

/** Manage the connected hubs: add, edit, remove, block, and ask them all whether they answer. */
export default function PeersPanel({ onLost }: { onLost?: () => void }) {
  const { t, intl } = useI18n();
  const [out, setOut] = useState<{ peers: AdminPeer[]; from_environment: boolean } | null>(null);
  const [url, setUrl] = useState("");
  const [name, setName] = useState("");
  const [reason, setReason] = useState("");
  const [acting, setActing] = useState<{ url: string; what: "remove" | "block" | "edit" } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api
      .adminPeers()
      .then(setOut)
      .catch((e) => {
        if (lost(e) && onLost) onLost();
        else setError((e as Error).message);
        setOut({ peers: [], from_environment: false });
      });
  }, [onLost]);
  useEffect(load, [load]);

  async function run(work: Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await work;
      setActing(null);
      load();
    } catch (e) {
      if (lost(e) && onLost) onLost();
      else setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (out === null) return <p className="muted">{t("admin.loading")}</p>;
  const open = acting ? out.peers.find((p) => p.url === acting.url) : undefined;
  const ready = url.trim() && reason.trim();
  return (
    <div className="stack loose">
      <p className="muted small">{t("admin.peers.lead")}</p>
      {out.from_environment && <p className="muted small">{t("admin.peers.fromEnv")}</p>}
      {error && <p className="error">{error}</p>}

      {open && acting?.what === "edit" && (
        <Edit
          peer={open}
          busy={busy}
          onCancel={() => setActing(null)}
          onGo={(n, h, why) => run(api.adminEditPeer(open.url, why, n, h))}
        />
      )}
      {open && acting?.what !== "edit" && (
        <Ask
          what={acting?.what === "block" ? "block" : "remove"}
          name={open.name || open.hub}
          busy={busy}
          onCancel={() => setActing(null)}
          onGo={(why) =>
            run(acting?.what === "block" ? api.adminBlock("hub", open.hub, why) : api.adminRemovePeer(open.url, why))
          }
        />
      )}

      {!out.peers.length ? (
        <p className="muted">{t("admin.peers.empty")}</p>
      ) : (
        <ul className="rows">
          {out.peers.map((p) => (
            <li key={p.url}>
              <span className="stack tight">
                <strong>{p.name || p.hub}</strong>
                <span className="muted small key-line">{p.url}</span>
                <span className="muted small">{p.hub}</span>
                {p.added_at && (
                  <span className="muted small">{t("admin.peers.added", { date: dayOf(p.added_at, intl) })}</span>
                )}
              </span>
              <span className="stack tight">
                {p.state === "removed" ? (
                  <span className="status no">{t("admin.peers.removed")}</span>
                ) : (
                  <Answers peer={p} />
                )}
                <Calibration peer={p} />
                {p.blocked && <span className="status no">{t("admin.peers.blocked")}</span>}
              </span>
              {p.state !== "removed" && (
                <span className="row">
                  <button className="quiet" onClick={() => setActing({ url: p.url, what: "edit" })}>
                    {t("admin.peers.edit")}
                  </button>
                  <button className="quiet" onClick={() => setActing({ url: p.url, what: "remove" })}>
                    {t("admin.peers.removeButton")}
                  </button>
                  {!p.blocked && (
                    <button className="quiet" onClick={() => setActing({ url: p.url, what: "block" })}>
                      {t("admin.peers.blockButton")}
                    </button>
                  )}
                </span>
              )}
            </li>
          ))}
        </ul>
      )}

      <button className="quiet self-start" disabled={busy} onClick={() => run(api.adminCheckPeers())}>
        {busy ? t("admin.peers.checking") : t("admin.peers.check")}
      </button>

      {/* One thing at a time: while a peer is being changed, the add form steps aside rather than offering a
          second "Reason, required" box next to the first. */}
      {!acting && (
        <form
          className="stack tight"
          onSubmit={(e) => {
            e.preventDefault();
            run(api.adminAddPeer(url.trim(), reason.trim(), name.trim())).then(() => {
              setUrl("");
              setName("");
              setReason("");
            });
          }}
        >
          <p className="eyebrow">{t("admin.peers.add")}</p>
          <label htmlFor="peer-url">{t("admin.peers.url")}</label>
          <input id="peer-url" value={url} onChange={(e) => setUrl(e.target.value)} />
          <label htmlFor="peer-new-name">{t("admin.peers.name")}</label>
          <input id="peer-new-name" value={name} onChange={(e) => setName(e.target.value)} />
          <label htmlFor="peer-new-reason">{t("admin.peers.reason")}</label>
          <input id="peer-new-reason" value={reason} onChange={(e) => setReason(e.target.value)} />
          <button type="submit" disabled={busy || !ready}>
            {t("admin.peers.addDo")}
          </button>
          {!ready && <p className="muted small">{t("admin.peers.reasonNeeded")}</p>}
        </form>
      )}
      <p className="muted small">{t("finder.cal.explain")}</p>
    </div>
  );
}
