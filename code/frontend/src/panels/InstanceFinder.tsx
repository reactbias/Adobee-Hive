import { useEffect, useMemo, useState } from "react";
import { api, apiOrigin, setChosenHub, type DirectoryHub } from "../api";
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
// the app is deployed against, and the person carries on.

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

function Row({
  hub,
  needed,
  onPick,
  onJoin,
}: {
  hub: DirectoryHub;
  needed: number;
  onPick: (hub: string) => void;
  onJoin: (hub: DirectoryHub) => void;
}) {
  const { t } = useI18n();
  const admission = ADMISSIONS.includes(hub.admission ?? "") ? hub.admission : "unknown";
  // A count we do not have is said, never formatted: `{n} entities` with nothing to put in it reached the screen
  // as a literal "{n} entities", and a null must not get as far as a formatter.
  const carries =
    typeof hub.entities === "number" ? t("finder.entities", { n: hub.entities }) : t("finder.entitiesUnknown");
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
      <footer className="hive-actions">
        <button onClick={() => onPick(hub.hub)} disabled={hub.blocked}>
          {t("finder.use")}
        </button>
        <button className="ghost" onClick={() => onJoin(hub)} disabled={!joinable(hub) || !hub.apply_at}>
          {t("finder.join")}
        </button>
        {!hub.blocked && !joinable(hub) && <p className="muted small">{t("finder.joinClosed")}</p>}
        {!hub.home && <p className="muted small">{t("finder.peerNotWired")}</p>}
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
 * The first screen: which Hive do you want to use, or join. Picking one remembers it for this tab and hands over
 * to the app; joining hands the row to the application form. `?hub=<id>` in the address skips this screen.
 */
export default function InstanceFinder({
  onPick,
  onJoin,
}: {
  onPick: (hub: string) => void;
  onJoin: (hub: DirectoryHub) => void;
}) {
  const { t, intl } = useI18n();
  const [hubs, setHubs] = useState<DirectoryHub[] | null>(null);
  const [fallback, setFallback] = useState(false);
  // How many scored introductions a verdict needs, from the hub itself, so "unproven" can say how far off it is.
  const [needed, setNeeded] = useState(MIN_EVIDENCE);
  const [query, setQuery] = useState("");
  const [accepting, setAccepting] = useState(false);
  const [proven, setProven] = useState(false);

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
            apply_at: "/api/hub/register",
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

  const shown = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase(intl);
    return (hubs ?? [])
      .filter((h) => !needle || [h.name, h.hub, h.description].join(" ").toLocaleLowerCase(intl).includes(needle))
      .filter((h) => !accepting || (h.accepting === true && joinable(h)))
      .filter((h) => !proven || readCalibration(h.error, h.verdict).reading !== "unproven")
      .sort((a, b) => label(a).localeCompare(label(b), intl));
  }, [hubs, query, accepting, proven, intl]);

  const choose = (hub: string) => {
    setChosenHub(hub);
    onPick(hub);
  };

  return (
    <section className="finder" id="finder">
      <h1>{t("finder.title")}</h1>
      <p>{t("finder.lead")}</p>
      {fallback && <p className="finder-draft">{t("finder.notDeployed")}</p>}
      <p className="finder-draft">{t("finder.pinned", { backend: apiOrigin() })}</p>
      {hubs === null ? (
        <p className="muted">{t("finder.loading")}</p>
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
          {shown.length ? (
            <ul className="hive-list">
              {shown.map((h) => (
                <Row key={h.hub} hub={h} needed={needed} onPick={choose} onJoin={onJoin} />
              ))}
            </ul>
          ) : (
            <p className="muted">{t("finder.noMatch")}</p>
          )}
        </>
      )}
      <p className="muted small">{t("finder.cal.explain")}</p>
    </section>
  );
}
