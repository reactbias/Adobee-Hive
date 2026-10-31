import { useEffect, useState } from "react";
import { api, apiOrigin, setChosenHub, type DirectoryHub } from "../api";
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
 * The first screen: which Hive do you want to use. Picking one remembers it for this tab and hands over to
 * the app. `?hub=<id>` in the address skips this screen entirely, which is what the pitch runbook uses.
 */
export default function InstanceFinder({ onPick }: { onPick: (hub: string) => void }) {
  const { t } = useI18n();
  const [hubs, setHubs] = useState<DirectoryHub[] | null>(null);
  const [fallback, setFallback] = useState(false);
  // How many scored introductions a verdict needs, from the hub itself, so "unproven" can say how far off it is.
  const [needed, setNeeded] = useState(MIN_EVIDENCE);

  useEffect(() => {
    let live = true;
    api
      .directory()
      .then((d) => {
        if (!live) return;
        setHubs(d.hubs);
        setNeeded(d.min_evidence ?? MIN_EVIDENCE);
      })
      .catch(() => {
        if (!live) return;
        setFallback(true);
        setHubs([
          {
            hub: "local",
            url: "",
            home: true,
            blocked: false,
            name: t("finder.thisHub"),
            description: t("finder.thisHubDescription"),
            accepting: true,
            error: null,
            error_stars: null,
            evidence: 0,
            verdict: "unproven",
            why: "",
          },
        ]);
      });
    return () => {
      live = false;
    };
    // The fallback row's text is in the page's language at the moment it is built; a switch re-renders the rest.
  }, [t]);

  const choose = (hub: string) => {
    setChosenHub(hub);
    onPick(hub);
  };

  return (
    <section className="finder" id="finder">
      <h1>{t("finder.title")}</h1>
      <p>{t("finder.lead")}</p>
      <p className="finder-draft">{t("finder.draft")}</p>
      {fallback && <p className="finder-draft">{t("finder.notDeployed")}</p>}
      <p className="finder-draft">{t("finder.pinned", { backend: apiOrigin() })}</p>
      {hubs === null ? (
        <p className="muted">{t("finder.loading")}</p>
      ) : (
        <ul className="finder-list">
          {hubs.map((h) => (
            <Row key={h.hub} hub={h} onPick={choose} needed={needed} />
          ))}
        </ul>
      )}
      <p className="muted small">{t("finder.cal.explain")}</p>
    </section>
  );
}
