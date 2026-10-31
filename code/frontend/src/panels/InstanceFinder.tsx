import { Component, useEffect, useState, type ReactNode } from "react";
import { ApiError, api, apiOrigin, setChosenHub, type Directory, type DirectoryHub } from "../api";
import { useI18n } from "../i18n";
import type { Key } from "../i18n/en";
import { readCalibration, stars } from "../lib/calibration";
import { moment, since } from "../lib/format";

// Before you can use a federated network you have to pick a door. This is the instances.social idea for Hives:
// a plain list of hubs with the one column a Mastodon directory cannot offer, how closely each hub's published
// ratings matched what real people found.
//
// Deliberately plain: a list, no animation, no layout cleverness, and a line on screen saying so. It is a first
// pass so that the work still to be done is visible rather than hidden behind a finished-looking screen.
//
// GET /api/hub/directory is not on `main` yet (PR #71). A 404 or a lost connection is not an error page here:
// the list falls back to one row for the hub the app is deployed against, and the person carries on.

const ADMISSIONS = ["open", "vetted", "invite", "closed"];
// What calibration.MIN_EVIDENCE is on the backend, for the one render before the directory answers.
const MIN_EVIDENCE = 3;

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

/** One hub, as five plain lines and a button. */
function Row({ hub, onPick, needed }: { hub: DirectoryHub; onPick: (hub: string) => void; needed: number }) {
  const { t } = useI18n();
  const admission = hub.admission && ADMISSIONS.includes(hub.admission) ? hub.admission : "";
  // A count we do not have is said, never formatted: `{n} entities` with nothing to put in it reached the screen
  // as a literal "{n} entities", and a null must not get as far as a formatter.
  const carries =
    typeof hub.entities === "number" ? t("finder.entities", { n: hub.entities }) : t("finder.entitiesUnknown");
  return (
    <li className="finder-row">
      <div className="stack tight">
        <h3>{hub.name || hub.hub}</h3>
        <p className="muted">{hub.description || t("finder.unknownDescription")}</p>
        <p className="finder-facts">
          <Accepting hub={hub} />
          {admission && <span className="muted">{t(`finder.admission.${admission}` as Key)}</span>}
          <span className="muted">{carries}</span>
        </p>
        <p className="finder-facts">
          <span className="eyebrow">{t("finder.cal.label")}</span>
          <Calibration hub={hub} needed={needed} />
        </p>
        <p className="finder-facts">
          <LastAsked hub={hub} />
        </p>
        {!hub.home && <p className="muted small">{t("finder.peerNotWired")}</p>}
      </div>
      <button onClick={() => onPick(hub.hub)} disabled={hub.blocked}>
        {t("finder.use")}
      </button>
    </li>
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
    entities: null,
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

/**
 * The first screen: which Hive do you want to use. Picking one remembers it for this tab and hands over to
 * the app. `?hub=<id>` in the address skips this screen entirely, which is what the pitch runbook uses.
 *
 * It always renders something. Loading says it is loading, a failure says what failed and offers a retry, and
 * either way this hub is listed so a person is never stuck on a screen with nothing to choose.
 */
export default function InstanceFinder({ onPick }: { onPick: (hub: string) => void }) {
  const { t } = useI18n();
  const [hubs, setHubs] = useState<DirectoryHub[] | null>(null);
  const [failed, setFailed] = useState<string>("");
  const [status, setStatus] = useState(0);
  const [slow, setSlow] = useState(false);
  const [attempt, setAttempt] = useState(0);
  // How many scored introductions a verdict needs, from the hub itself, so "unproven" can say how far off it is.
  const [needed, setNeeded] = useState(MIN_EVIDENCE);

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

  const choose = (hub: string) => {
    setChosenHub(hub);
    onPick(hub);
  };

  const listed = hubs ?? [];
  return (
    <section className="finder" id="finder">
      <h1>{t("finder.title")}</h1>
      <p>{t("finder.lead")}</p>
      <p className="finder-draft">{t("finder.draft")}</p>
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
      ) : (
        <Rows onBroken={() => setFailed("finder.failed.render")}>
          <ul className="finder-list">
            {listed.map((h) => (
              <Row key={h.hub} hub={h} onPick={choose} needed={needed} />
            ))}
          </ul>
        </Rows>
      )}
      {hubs !== null && listed.length === 0 && (
        <ul className="finder-list">
          <Row hub={thisHub(t)} onPick={choose} needed={needed} />
        </ul>
      )}
      <p className="muted small">{t("finder.cal.explain")}</p>
    </section>
  );
}
