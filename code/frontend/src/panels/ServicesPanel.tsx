import { useCallback, useEffect, useState } from "react";
import { ApiError, api, type AdminService } from "../api";
import { useI18n } from "../i18n";
import { dayOf } from "../lib/format";

// The optional integrations, and the keys they need. Everything here is optional on purpose: the hub answers with
// no key at all, and each row says what it costs to leave off rather than nagging for one.
//
// A key is write-only. It is typed once and never shown again: the row carries presence, a fingerprint and the
// last four characters, which is enough for an operator to tell which key is loaded and no use to a shoulder.
// The panel also says plainly that the key is stored on this hub in the clear unless the host encrypts its disk,
// because a protection we did not build must not be implied.

const lost = (e: unknown) => e instanceof ApiError && (e.status === 401 || e.status === 403);

/** Whether a key is set, and from where. The environment is still the seed, so "where" is the useful part. */
function Configured({ service }: { service: AdminService }) {
  const { t } = useI18n();
  if (!service.configured) return <span className="status">{t("admin.services.off")}</span>;
  return (
    <span className="status ok">
      {t(service.source === "stored" ? "admin.services.fromPanel" : "admin.services.fromEnv")}
    </span>
  );
}

/** How the last test went. Untested is not a failure and is not drawn as one. */
function Tested({ service }: { service: AdminService }) {
  const { t, intl } = useI18n();
  if (service.working === null) return <span className="status">{t("admin.services.untested")}</span>;
  return (
    <span className="stack tight">
      <span className={service.working ? "status ok" : "status no"}>
        {t(service.working ? "admin.services.works" : "admin.services.fails")}
      </span>
      {service.checked_at && (
        <span className="muted small">{t("admin.services.testedOn", { date: dayOf(service.checked_at, intl) })}</span>
      )}
      {!service.working && service.last_error && <span className="muted small">{service.last_error}</span>}
    </span>
  );
}

/** One integration: what it is for, what the hub does without it, and the two things to do about it. */
function Row({
  service,
  busy,
  onSet,
  onClear,
  onTest,
}: {
  service: AdminService;
  busy: boolean;
  onSet: (secret: string) => void;
  onClear: () => void;
  onTest: () => void;
}) {
  const { t } = useI18n();
  const [secret, setSecret] = useState("");
  const [confirming, setConfirming] = useState(false);
  const field = `service-key-${service.name}`;
  return (
    <section className="admin-card stack tight">
      <h3>{service.label}</h3>
      <p className="muted small">{service.purpose}</p>
      <div className="statuses">
        <Configured service={service} />
        <Tested service={service} />
      </div>
      {service.without && <p className="muted small">{t("admin.services.without", { what: service.without })}</p>}
      {service.stored && (
        <p className="muted small">
          {t("admin.services.loaded", { tail: service.last_four, fingerprint: service.fingerprint })}
        </p>
      )}
      <p className="muted small">{t("admin.services.envName", { name: service.env })}</p>

      {confirming ? (
        <section className="stack tight">
          <p>{t("admin.services.clearConfirm", { label: service.label })}</p>
          <p className="muted small">
            {t(service.source === "environment" ? "admin.services.clearToEnv" : "admin.services.clearWill", {
              what: service.without,
            })}
          </p>
          <div className="row">
            <button
              onClick={() => {
                setConfirming(false);
                onClear();
              }}
              disabled={busy}
            >
              {t("admin.services.clearDo")}
            </button>
            <button className="quiet" onClick={() => setConfirming(false)} disabled={busy}>
              {t("admin.services.cancel")}
            </button>
          </div>
        </section>
      ) : (
        <form
          className="stack tight"
          onSubmit={(e) => {
            e.preventDefault();
            onSet(secret.trim());
            setSecret("");
          }}
        >
          <label htmlFor={field}>{t(service.stored ? "admin.services.replace" : "admin.services.key")}</label>
          <input
            id={field}
            type="password"
            autoComplete="off"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
          />
          <div className="row">
            <button type="submit" disabled={busy || !secret.trim()}>
              {t("admin.services.save")}
            </button>
            {service.testable && service.configured && (
              <button type="button" className="quiet" onClick={onTest} disabled={busy}>
                {busy ? t("admin.services.testing") : t("admin.services.test")}
              </button>
            )}
            {service.stored && (
              <button type="button" className="quiet" onClick={() => setConfirming(true)} disabled={busy}>
                {t("admin.services.clear")}
              </button>
            )}
          </div>
        </form>
      )}
    </section>
  );
}

/** Set, clear and test the keys of the hub's optional integrations. Nothing here ever shows a key. */
export default function ServicesPanel({ onLost }: { onLost?: () => void }) {
  const { t } = useI18n();
  const [rows, setRows] = useState<AdminService[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api
      .adminServices()
      .then((out) => setRows(out.services))
      .catch((e) => {
        if (lost(e) && onLost) onLost();
        else setError((e as Error).message);
        setRows([]);
      });
  }, [onLost]);
  useEffect(load, [load]);

  async function run(work: Promise<unknown>) {
    setBusy(true);
    setError("");
    try {
      await work;
      load();
    } catch (e) {
      if (lost(e) && onLost) onLost();
      else setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  // A test is shown from what the call returned, not from a reload. A key inherited from this hub's
  // environment has no stored row to write a verdict to, so reloading would quietly throw the answer
  // away and leave "not tested yet" on screen after a test that did run.
  async function test(name: string) {
    setBusy(true);
    setError("");
    try {
      const out = await api.adminCheckService(name);
      setRows((current) => (current ?? []).map((s) => (s.name === name ? { ...s, ...out } : s)));
    } catch (e) {
      if (lost(e) && onLost) onLost();
      else setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (rows === null) return <p className="muted">{t("admin.loading")}</p>;
  return (
    <div className="stack loose">
      <p className="muted small">{t("admin.services.lead")}</p>
      {/* Said before any key is typed, not after. The backend ships the same sentence for curl. */}
      <p className="muted small">{t("admin.services.storage")}</p>
      {/* Each service describes itself in English, as the settings form does. */}
      <p className="muted small">{t("admin.settingsEnglish")}</p>
      {error && <p className="error">{error}</p>}
      {rows.map((s) => (
        <Row
          key={s.name}
          service={s}
          busy={busy}
          onSet={(secret) => run(api.adminSetServiceKey(s.name, secret))}
          onClear={() => run(api.adminClearServiceKey(s.name))}
          onTest={() => test(s.name)}
        />
      ))}
    </div>
  );
}
