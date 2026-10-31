import { Component, useEffect, useState, type ReactNode } from "react";
import {
  ApiError,
  api,
  apiOrigin,
  blockedAsMixedContent,
  setChosenHub,
  type Directory,
  type DirectoryHub,
} from "../api";
import { useI18n } from "../i18n";
import type { Key } from "../i18n/en";
import { readCalibration, stars } from "../lib/calibration";
import { moment, since } from "../lib/format";

// Before you can use a federated network you have to pick a door: instances.social's job, for Hives. Each hive is
// shown as the three things a person is deciding between, not as its field list: what it carries, whether it
// will have them, and whether it can be trusted. Trust is the column a Mastodon directory cannot offer, how
// closely a hive's published ratings matched what real people found.
//
// Three readings have to be right or the page lies. Calibration is lower-is-better and "unproven" means too
// little evidence, not zero. `accepting: null` and `entities: null` mean nobody has asked that hive yet, a third
// state, not "no". And admission comes before the Join button, so nobody writes an application for a closed door.
//
// The hive you are on is marked, not pinned first: the list is in name order for everyone.
//
// A 404 or a lost connection on the directory is not an error page: the list falls back to one row for the hub
// the app is deployed against, and the person carries on. Picking a row points the app at that hub's address.

const ADMISSIONS = ["open", "vetted", "invite", "closed", "unknown"];
// What calibration.MIN_EVIDENCE is on the backend, for the one render before the directory answers.
const MIN_EVIDENCE = 3;

/** Whether this hive takes applications at all, as far as anyone knows. */
const joinable = (hub: DirectoryHub) => !hub.blocked && hub.admission !== "closed" && hub.accepting !== false;

const label = (hub: DirectoryHub) => hub.name || hub.hub;

/**
 * What calibration to say, in one sentence, in the page's language. Lower is better; negative means the hub
 * undersold itself.
 *
 * One sentence on purpose: the verdict and the evidence count used to be rendered as two spans that repeated
 * each other ("Unproven, too few scored introductions" next to "0 scored introductions"). The backend's own
 * `why` is the detail, so it goes in the title rather than being reassembled here.
 */
function Calibration({ hub, needed }: { hub: DirectoryHub; needed: number }) {
  const { t, intl } = useI18n();
  const { reading, stars: n } = readCalibration(hub.error, hub.verdict);
  const evidence = hub.evidence ?? 0;
  const line =
    reading === "unproven"
      ? evidence > 0
        ? t("finder.cal.line.unprovenSome", { n: evidence, needed })
        : t("finder.cal.line.unprovenNone")
      : t(`finder.cal.line.${reading}` as Key, { stars: stars(n, intl), n: evidence });
  const tone = reading === "unproven" ? "" : reading === "over" ? "no" : "ok";
  return (
    <span className={`status ${tone}`} title={hub.why || undefined}>
      {line}
    </span>
  );
}

/**
 * Whether this hub is taking members: yes, no, or not known yet. Three states, not two.
 *
 * `accepting: null` means nobody has asked the peer. Rendering that as "Not accepting members" advertised a hub
 * that might be wide open as closed, which is a different and false claim.
 */
function Accepting({ hub }: { hub: DirectoryHub }) {
  const { t } = useI18n();
  if (hub.accepting === null || hub.accepting === undefined)
    return <span className="status">{t("finder.acceptingUnknown")}</span>;
  return (
    <span className={`status ${hub.accepting ? "ok" : "no"}`}>
      {t(hub.accepting ? "finder.accepting" : "finder.closed")}
    </span>
  );
}

/**
 * When this hub was last asked what it carries, as relative time with the exact moment in the title.
 *
 * "This hub has not been asked what it carries" was permanently true because nothing ever asked. Now it is only
 * said when it is still true, and a failed ask says so while the row keeps the last answer that did arrive.
 */
function LastAsked({ hub }: { hub: DirectoryHub }) {
  const { t, intl } = useI18n();
  if (hub.home) return <span className="muted small">{t("finder.asked.home")}</span>;
  if (!hub.last_asked) return <span className="muted small">{t("finder.asked.never")}</span>;
  const when = since(hub.last_asked, intl);
  const answered = hub.last_asked_ok !== false;
  return (
    <span className="muted small" title={moment(hub.last_asked, intl)}>
      {answered ? t("finder.asked.ok", { when }) : t("finder.asked.failed", { when })}
      {!answered && hub.last_answered
        ? ` — ${t("finder.asked.lastKnown", { when: since(hub.last_answered, intl) })}`
        : ""}
    </span>
  );
}

/** One hub: the three questions, then Use and Join. */
function Row({
  hub,
  needed,
  onPick,
  onJoin,
}: {
  hub: DirectoryHub;
  needed: number;
  onPick: (hub: DirectoryHub) => void;
  onJoin: (hub: DirectoryHub) => void;
}) {
  const { t } = useI18n();
  // Mixed content is the one case a pick genuinely cannot be honoured: an HTTPS page may not call an http:// hub,
  // the browser blocks it before any request leaves, and no header on either side changes that. Say so, here,
  // rather than switching and then failing on every call.
  const mixed = !hub.home && !!hub.url && blockedAsMixedContent(hub.url);
  // And a hub we have no address for cannot be called either. Letting it be picked would put its name in the
  // header while every call still went to the hub we are on, which is the bug this whole screen is about.
  const noAddress = !hub.home && !hub.url;
  const unreachable = mixed || noAddress;
  const admission = ADMISSIONS.includes(hub.admission ?? "") ? (hub.admission ?? "unknown") : "unknown";
  // A count we do not have is said, never formatted: `{n} entities` with nothing to put in it reached the screen
  // as a literal "{n} entities", and a null must not get as far as a formatter.
  const carries =
    typeof hub.entities === "number" ? t("finder.entities", { n: hub.entities }) : t("finder.entitiesUnknown");
  const canJoin = joinable(hub) && !!hub.apply_at && !unreachable;
  return (
    <li className={`hive${hub.home ? " hive--home" : ""}`}>
      <header className="hive-head">
        <div className="stack tight">
          <h3>{label(hub)}</h3>
          {hub.name && <p className="muted small">{hub.hub}</p>}
        </div>
        {hub.home && <span className="hive-badge">{t("finder.home")}</span>}
        {hub.blocked && <span className="status no">{t("finder.blocked")}</span>}
      </header>
      <dl className="hive-questions">
        <div>
          <dt className="eyebrow">{t("finder.q.carries")}</dt>
          <dd>{hub.description || t("finder.unknownDescription")}</dd>
          <dd className="muted">{carries}</dd>
          <dd>
            <LastAsked hub={hub} />
          </dd>
        </div>
        <div>
          <dt className="eyebrow">{t("finder.q.admits")}</dt>
          <dd>
            <Accepting hub={hub} />
          </dd>
          <dd className="muted">{t(`finder.admission.${admission}` as Key)}</dd>
        </div>
        <div>
          <dt className="eyebrow">{t("finder.q.trust")}</dt>
          <dd>
            <Calibration hub={hub} needed={needed} />
          </dd>
        </div>
      </dl>
      {mixed && <p className="muted small">{t("finder.mixedContent", { url: hub.url })}</p>}
      {noAddress && <p className="muted small">{t("finder.noAddress")}</p>}
      <footer className="hive-actions">
        <button onClick={() => onPick(hub)} disabled={hub.blocked || unreachable}>
          {t("finder.use")}
        </button>
        <button className="ghost" onClick={() => onJoin(hub)} disabled={!canJoin}>
          {t("finder.join")}
        </button>
        {!hub.blocked && !joinable(hub) && <p className="muted small">{t("finder.joinClosed")}</p>}
      </footer>
    </li>
  );
}

/** A filter that is either on or off, read out as a pressed button. */
function Toggle({ on, onChange, children }: { on: boolean; onChange: (on: boolean) => void; children: string }) {
  return (
    <button type="button" className="quiet hive-filter" aria-pressed={on} onClick={() => onChange(!on)}>
      {children}
    </button>
  );
}

/**
 * A list that cannot take the page down with it.
 *
 * The finder used to disappear completely: `GET /api/hub/directory` answering 200 with a body that was not
 * `{hubs: [...]}` set `hubs` to `undefined`, which is not `null`, so the loading branch was skipped and
 * `hubs.map` threw during render. React has no error boundary above this, so it unmounted the whole root and
 * the page went blank — header, finder and all. Verified in a browser: `root.innerHTML` was the empty string.
 *
 * The shape is checked before it is rendered, so that cannot happen again. This boundary is the second line:
 * whatever one bad row does, the heading, the explanation and the way out stay on screen.
 */
class Rows extends Component<{ children: ReactNode; onBroken: (reason: string) => void }, { broken: boolean }> {
  state = { broken: false };

  /** Render nothing in place of the list; the section around it reports the failure and offers a retry. */
  static getDerivedStateFromError() {
    return { broken: true };
  }

  /** Tell the section what went wrong, so it says something rather than showing a gap. */
  componentDidCatch(error: Error) {
    this.props.onBroken(error.message || "render");
  }

  render() {
    return this.state.broken ? null : this.props.children;
  }
}

/** This hub, as the one row that needs nobody's permission. Shown whenever the directory cannot be read. */
function thisHub(t: (key: Key) => string): DirectoryHub {
  return {
    hub: "local",
    url: "",
    home: true,
    blocked: false,
    name: t("finder.thisHub"),
    description: t("finder.thisHubDescription"),
    accepting: true,
    apply_at: "/api/hub/register",
    error: null,
    error_stars: null,
    evidence: 0,
    verdict: "unproven",
    why: "",
  };
}

/**
 * The rows of a directory answer, taking nothing on trust.
 *
 * A hub is only a hub if it has an id to pick it by. Anything else in the list is dropped rather than rendered,
 * and an answer that is not a list at all is a failed read with a reason — never a crash mid-render.
 */
export function hubsIn(answer: unknown): DirectoryHub[] {
  const rows = (answer as Directory | null)?.hubs;
  if (!Array.isArray(rows)) throw new Error("shape");
  return rows.filter((row): row is DirectoryHub => !!row && typeof row === "object" && typeof row.hub === "string");
}

/** Which sentence to show for a failed read. A 404 is a hub without the endpoint yet, not a broken one. */
function whyFailed(err: unknown): Key {
  if (err instanceof Error && err.message === "shape") return "finder.failed.shape";
  if (err instanceof ApiError && err.status === 404) return "finder.notDeployed";
  if (err instanceof ApiError) return "finder.failed.status";
  return "finder.failed.read";
}

// A directory read that takes longer than this stops being something to wait for and becomes something to say.
// The request is not abandoned: a slow hub that answers later still fills the list in.
const SLOW_MS = 15_000;

/** Search, filters and name order. Lives under the error boundary: a row that throws must not take the page. */
function HiveList({
  hubs,
  query,
  accepting,
  proven,
  needed,
  onPick,
  onJoin,
}: {
  hubs: DirectoryHub[];
  query: string;
  accepting: boolean;
  proven: boolean;
  needed: number;
  onPick: (hub: DirectoryHub) => void;
  onJoin: (hub: DirectoryHub) => void;
}) {
  const { t, intl } = useI18n();
  const needle = query.trim().toLocaleLowerCase(intl);
  const shown = hubs
    .filter((h) => !needle || [h.name, h.hub, h.description].join(" ").toLocaleLowerCase(intl).includes(needle))
    .filter((h) => !accepting || (h.accepting === true && joinable(h)))
    .filter((h) => !proven || readCalibration(h.error, h.verdict).reading !== "unproven")
    .sort((a, b) => label(a).localeCompare(label(b), intl));
  if (!shown.length) return <p className="muted">{t("finder.noMatch")}</p>;
  return (
    <ul className="hive-list">
      {shown.map((h) => (
        <Row key={h.hub} hub={h} needed={needed} onPick={onPick} onJoin={onJoin} />
      ))}
    </ul>
  );
}

/**
 * The first screen: which Hive do you want to use, or join. Picking one remembers it for this tab and hands over
 * to the app; joining hands the row to the application form. `?hub=<id>` in the address skips this screen.
 *
 * It always renders something. Loading says it is loading, a failure says what failed and offers a retry, and
 * either way this hub is listed so a person is never stuck on a screen with nothing to choose.
 */
export default function InstanceFinder({
  onPick,
  onJoin,
}: {
  onPick: (hub: string) => void;
  onJoin: (hub: DirectoryHub) => void;
}) {
  const { t } = useI18n();
  const [hubs, setHubs] = useState<DirectoryHub[] | null>(null);
  const [failed, setFailed] = useState<string>("");
  const [status, setStatus] = useState(0);
  const [slow, setSlow] = useState(false);
  const [attempt, setAttempt] = useState(0);
  // How many scored introductions a verdict needs, from the hub itself, so "unproven" can say how far off it is.
  const [needed, setNeeded] = useState(MIN_EVIDENCE);
  const [query, setQuery] = useState("");
  const [accepting, setAccepting] = useState(false);
  const [proven, setProven] = useState(false);

  useEffect(() => {
    let live = true;
    setSlow(false);
    // Nothing is cleared on a retry: the list that is already on screen stays until a better one arrives.
    const timer = setTimeout(() => live && setSlow(true), SLOW_MS);
    api
      .directory()
      .then((answer) => {
        if (!live) return;
        setHubs(hubsIn(answer));
        setNeeded((answer as Directory)?.min_evidence ?? MIN_EVIDENCE);
        setFailed("");
        setSlow(false);
      })
      .catch((err: unknown) => {
        if (!live) return;
        // Whatever went wrong, this hub is still here and still pickable.
        setHubs((known) => (known?.length ? known : [thisHub(t)]));
        setStatus(err instanceof ApiError ? err.status : 0);
        setFailed(whyFailed(err));
        setSlow(false);
      })
      .finally(() => clearTimeout(timer));
    return () => {
      live = false;
      clearTimeout(timer);
    };
    // `attempt` is the retry button; `t` rebuilds the fallback row in the page's language after a switch.
  }, [t, attempt]);

  // Picking a Hive points the app at it: the id for the screen, the URL for every call after this one. The home
  // row keeps "" so the app stays on the backend this build was given.
  const choose = (picked: DirectoryHub) => {
    setChosenHub(picked.hub, picked.home ? "" : picked.url || "");
    onPick(picked.hub);
  };

  const listed = hubs ?? [];
  return (
    <section className="finder" id="finder">
      <h1>{t("finder.title")}</h1>
      <p>{t("finder.lead")}</p>
      {(failed || slow) && (
        <p className="finder-draft" role="status">
          {failed ? t(failed as Key, { status }) : t("finder.slow")}{" "}
          <button className="quiet" onClick={() => setAttempt((n) => n + 1)}>
            {t("finder.retry")}
          </button>
        </p>
      )}
      <p className="finder-draft">{t("finder.pinned", { backend: apiOrigin() })}</p>
      {hubs === null ? (
        <p className="muted">{t("finder.loading")}</p>
      ) : listed.length === 0 ? (
        <ul className="hive-list">
          <Row hub={thisHub(t)} needed={needed} onPick={choose} onJoin={onJoin} />
        </ul>
      ) : (
        <>
          <div className="hive-search">
            <input
              type="search"
              aria-label={t("finder.search")}
              placeholder={t("finder.search")}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <div className="hive-filters" role="group" aria-label={t("finder.filter.label")}>
              <Toggle on={accepting} onChange={setAccepting}>
                {t("finder.filter.accepting")}
              </Toggle>
              <Toggle on={proven} onChange={setProven}>
                {t("finder.filter.proven")}
              </Toggle>
            </div>
          </div>
          <Rows onBroken={() => setFailed("finder.failed.render")}>
            <HiveList
              hubs={listed}
              query={query}
              accepting={accepting}
              proven={proven}
              needed={needed}
              onPick={choose}
              onJoin={onJoin}
            />
          </Rows>
        </>
      )}
      <p className="muted small">{t("finder.cal.explain")}</p>
    </section>
  );
}
