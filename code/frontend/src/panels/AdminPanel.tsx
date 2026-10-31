import { useCallback, useEffect, useState } from "react";
import {
  adminToken,
  ApiError,
  api,
  setAdminToken,
  type AdminNeighbours,
  type AdminOverview,
  type AdminSettings,
  type Application,
  type Blocklist,
  type DirectoryHub,
  type Peer,
  type SettingsField,
} from "../api";
import { useI18n } from "../i18n";
import type { Key } from "../i18n/en";
import { readCalibration, stars } from "../lib/calibration";

// Running the hub, from a browser instead of curl. The hub's password buys a short-lived session token which
// lives in this tab's sessionStorage only; a 401 or 403 from anything drops it and asks again.
//
// Two of these views are built against endpoints that are not on `main` yet (the signup queue, PR #71). A 404 is
// not an error here, it is "not deployed on this hub": the view says so and the rest of the panel keeps working.

const VIEWS = ["overview", "applications", "blocklist", "neighbours"] as const;
type View = (typeof VIEWS)[number];

const lost = (e: unknown) => e instanceof ApiError && (e.status === 401 || e.status === 403);
const missing = (e: unknown) => e instanceof ApiError && e.status === 404;

/** Calibration, labelled: lower is better, and a negative error means the hub undersold what it offered. */
function Calibration({ peer }: { peer: Peer | DirectoryHub }) {
  const { t, intl } = useI18n();
  const { reading, stars: n } = readCalibration(peer.error, peer.verdict);
  if (reading === "unproven") return <span className="status">{t("finder.cal.unproven")}</span>;
  return (
    <span className={`status ${reading === "over" ? "no" : "ok"}`}>
      {t(`finder.cal.${reading}` as Key, { stars: stars(n, intl) })}
    </span>
  );
}

/** The password form. Nothing else is on screen until it succeeds. */
function SignIn({ onToken }: { onToken: (token: string) => void }) {
  const { t } = useI18n();
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [wait, setWait] = useState(0);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setWait(0);
    try {
      const session = await api.adminLogin(password);
      setPassword("");
      setAdminToken(session.token);
      onToken(session.token);
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) setWait(Number(err.retryAfter) || 1);
      else if (err instanceof ApiError && err.status === 503) setError(t("admin.disabled"));
      else if (err instanceof ApiError && err.status === 403) setError(t("admin.wrongPassword"));
      else setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="admin-signin stack" onSubmit={submit}>
      <h1>{t("admin.title")}</h1>
      <p className="muted">{t("admin.signInLead")}</p>
      <label htmlFor="admin-password">{t("admin.password")}</label>
      <input
        id="admin-password"
        type="password"
        autoComplete="current-password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />
      <button type="submit" disabled={busy || !password}>
        {busy ? t("admin.signingIn") : t("admin.signIn")}
      </button>
      {wait > 0 && <p className="error">{t("admin.lockedOut", { s: wait })}</p>}
      {error && <p className="error">{error}</p>}
    </form>
  );
}

/** The three stores, counted, plus the hub's own settings rendered from the fields the API hands over. */
function Overview({ overview, settings }: { overview: AdminOverview | null; settings: AdminSettings | null }) {
  const { t } = useI18n();
  if (!overview) return <p className="muted">{t("admin.loading")}</p>;
  const counts: [Key, number][] = [
    ["admin.count.entities", overview.index.entities],
    ["admin.count.peers", overview.neighbours.configured],
    ["admin.count.blocked", overview.blocklist.hubs + overview.blocklist.entities],
  ];
  return (
    <div className="stack loose">
      <ul className="rows">
        {counts.map(([key, n]) => (
          <li key={key}>
            <span>{t(key)}</span>
            <strong>{n}</strong>
          </li>
        ))}
      </ul>
      <section className="stack tight">
        <p className="eyebrow">{t("admin.settings")}</p>
        {/* Generated from GET /api/admin/settings: label, help, value and options come from the hub itself, so a
            field added to the backend appears here with no change to this file. The hub's own labels are English
            only; translating an operator's settings form needs the backend to ship the four languages first. */}
        {settings ? (
          <ul className="rows admin-fields">
            {settings.fields.map((f: SettingsField) => (
              <li key={f.key}>
                <span className="stack tight">
                  <label htmlFor={`setting-${f.key}`}>{f.label}</label>
                  <span className="muted small">{f.help}</span>
                </span>
                {f.options ? (
                  <select id={`setting-${f.key}`} value={String(f.value ?? "")} disabled>
                    {f.options.map((o) => (
                      <option key={o} value={o}>
                        {o}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input id={`setting-${f.key}`} value={String(f.value ?? "")} readOnly />
                )}
              </li>
            ))}
          </ul>
        ) : (
          <p className="muted">{t("admin.loading")}</p>
        )}
        <p className="muted small">{t("admin.settingsReadOnly")}</p>
      </section>
    </div>
  );
}

/** The signup queue: admit, or refuse with a reason the applicant is told. */
function Applications({ onLost }: { onLost: () => void }) {
  const { t } = useI18n();
  const [rows, setRows] = useState<Application[] | null>(null);
  const [notDeployed, setNotDeployed] = useState(false);
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api
      .adminApplications("pending")
      .then((out) => setRows(out.applications))
      .catch((e) => {
        if (missing(e)) setNotDeployed(true);
        else if (lost(e)) onLost();
        else setError((e as Error).message);
        setRows([]);
      });
  }, [onLost]);
  useEffect(load, [load]);

  async function decide(id: string, admit: boolean) {
    setError("");
    try {
      await api.adminDecide(id, admit, reasons[id] ?? "");
      load();
    } catch (e) {
      if (lost(e)) onLost();
      else setError((e as Error).message);
    }
  }

  if (notDeployed) return <p className="muted">{t("admin.applications.notDeployed")}</p>;
  if (rows === null) return <p className="muted">{t("admin.loading")}</p>;
  if (!rows.length) return <p className="muted">{t("admin.applications.empty")}</p>;

  return (
    <div className="stack loose">
      {error && <p className="error">{error}</p>}
      {rows.map((a) => {
        const reason = (reasons[a.id] ?? "").trim();
        return (
          <section key={a.id} className="admin-card stack tight">
            <h3>{a.name || a.entity_id}</h3>
            <p className="muted small">
              {t("admin.applications.who", { id: a.entity_id, kind: a.kind })} ·{" "}
              {t(`admin.custody.${a.custody === "hub" ? "hub" : "owner"}` as Key)}
            </p>
            <ul className="rows tight">
              {a.checks.map((c) => (
                <li key={c.check}>
                  <span className={`status ${c.ok ? "ok" : "no"}`}>
                    {t(c.ok ? "admin.check.passed" : "admin.check.failed")}
                  </span>
                  <span className="muted small">{c.check}</span>
                </li>
              ))}
            </ul>
            <label htmlFor={`refuse-${a.id}`}>{t("admin.applications.reason")}</label>
            <input
              id={`refuse-${a.id}`}
              value={reasons[a.id] ?? ""}
              onChange={(e) => setReasons({ ...reasons, [a.id]: e.target.value })}
            />
            <div className="row">
              <button onClick={() => decide(a.id, true)}>{t("admin.applications.admit")}</button>
              <button className="quiet" onClick={() => decide(a.id, false)} disabled={!reason}>
                {t("admin.applications.refuse")}
              </button>
            </div>
            {!reason && <p className="muted small">{t("admin.applications.reasonNeeded")}</p>}
          </section>
        );
      })}
    </div>
  );
}

/** Everything this hub has shut out, with the reason, and the two ways to change it. */
function BlocklistView({ onLost }: { onLost: () => void }) {
  const { t } = useI18n();
  const [list, setList] = useState<Blocklist | null>(null);
  const [kind, setKind] = useState("hub");
  const [subject, setSubject] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");

  const load = useCallback(() => {
    api
      .adminBlocklist()
      .then(setList)
      .catch((e) => setError((e as Error).message));
  }, []);
  useEffect(load, [load]);

  async function run(work: Promise<unknown>) {
    setError("");
    try {
      await work;
      load();
    } catch (e) {
      if (lost(e)) onLost();
      else setError((e as Error).message);
    }
  }

  const ready = subject.trim() && reason.trim();
  return (
    <div className="stack loose">
      <form
        className="stack tight"
        onSubmit={(e) => {
          e.preventDefault();
          run(api.adminBlock(kind, subject.trim(), reason.trim())).then(() => {
            setSubject("");
            setReason("");
          });
        }}
      >
        <label htmlFor="block-kind">{t("admin.block.kind")}</label>
        <select id="block-kind" value={kind} onChange={(e) => setKind(e.target.value)}>
          {(list?.kinds ?? ["hub", "entity"]).map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
        </select>
        <label htmlFor="block-subject">{t("admin.block.subject")}</label>
        <input id="block-subject" value={subject} onChange={(e) => setSubject(e.target.value)} />
        <label htmlFor="block-reason">{t("admin.block.reason")}</label>
        <input id="block-reason" value={reason} onChange={(e) => setReason(e.target.value)} />
        <button type="submit" disabled={!ready}>
          {t("admin.block.add")}
        </button>
        {!ready && <p className="muted small">{t("admin.block.reasonNeeded")}</p>}
      </form>
      {error && <p className="error">{error}</p>}
      {list === null ? (
        <p className="muted">{t("admin.loading")}</p>
      ) : !list.entries.length ? (
        <p className="muted">{t("admin.block.empty")}</p>
      ) : (
        <ul className="rows">
          {list.entries.map((b) => (
            <li key={`${b.kind}/${b.subject}`}>
              <span className="stack tight">
                <strong>{b.subject}</strong>
                <span className="muted small">
                  {b.kind} · {b.reason}
                </span>
              </span>
              <button className="quiet" onClick={() => run(api.adminUnblock(b.kind, b.subject))}>
                {t("admin.block.lift")}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** The peers, each with how closely its published ratings held up. */
function Neighbours() {
  const { t } = useI18n();
  const [out, setOut] = useState<AdminNeighbours | null>(null);
  useEffect(() => {
    api
      .adminNeighbours()
      .then(setOut)
      .catch(() => setOut({ peers: [], blocked_hubs: [] }));
  }, []);
  if (out === null) return <p className="muted">{t("admin.loading")}</p>;
  if (!out.peers.length) return <p className="muted">{t("admin.neighbours.empty")}</p>;
  return (
    <div className="stack loose">
      <p className="muted small">{t("finder.cal.explain")}</p>
      <ul className="rows">
        {out.peers.map((p) => (
          <li key={p.hub}>
            <span className="stack tight">
              <strong>{p.hub}</strong>
              <span className="muted small">{p.why}</span>
            </span>
            <span className="stack tight">
              <Calibration peer={p} />
              <span className="muted small">{t("finder.cal.evidence", { n: p.evidence })}</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Chapter 3, operators only (`?admin`): sign in with the hub's password, then run the hub. */
export default function AdminPanel({ onLeave }: { onLeave?: () => void }) {
  const { t } = useI18n();
  const [token, setToken] = useState(() => adminToken());
  const [view, setView] = useState<View>("overview");
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [settings, setSettings] = useState<AdminSettings | null>(null);

  const signOut = useCallback(() => {
    setAdminToken("");
    setToken("");
    setOverview(null);
    setSettings(null);
  }, []);

  useEffect(() => {
    if (!token) return;
    api.adminOverview().then(setOverview).catch(signOut);
    api.adminSettings().then(setSettings).catch(signOut);
  }, [token, signOut]);

  if (!token) return <SignIn onToken={setToken} />;

  return (
    <section className="admin stack loose" id="admin">
      <div className="row admin-head">
        <h1>{t("admin.title")}</h1>
        <div className="row">
          {onLeave && (
            <button className="quiet" onClick={onLeave}>
              {t("admin.backToApp")}
            </button>
          )}
          <button
            className="quiet"
            onClick={() => {
              api.adminLogout().catch(() => undefined);
              signOut();
            }}
          >
            {t("admin.signOut")}
          </button>
        </div>
      </div>
      <div className="tabs" role="tablist" aria-label={t("admin.title")}>
        {VIEWS.map((v) => (
          <button
            key={v}
            role="tab"
            id={`admin-tab-${v}`}
            aria-selected={view === v}
            aria-controls="admin-tabpanel"
            className={view === v ? "tab on" : "tab"}
            onClick={() => setView(v)}
          >
            {t(`admin.view.${v}` as Key)}
          </button>
        ))}
      </div>
      <div id="admin-tabpanel" role="tabpanel" aria-labelledby={`admin-tab-${view}`}>
        {view === "overview" && <Overview overview={overview} settings={settings} />}
        {view === "applications" && <Applications onLost={signOut} />}
        {view === "blocklist" && <BlocklistView onLost={signOut} />}
        {view === "neighbours" && <Neighbours />}
      </div>
    </section>
  );
}
