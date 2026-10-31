import { useEffect, useState } from "react";
import { api, setChosenHub, type DirectoryHub } from "../api";
import { useI18n } from "../i18n";
import type { Key } from "../i18n/en";
import { readCalibration, stars } from "../lib/calibration";

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

/** What calibration to say, in the page's language. Lower is better; negative means the hub undersold itself. */
function Calibration({ hub }: { hub: DirectoryHub }) {
  const { t, intl } = useI18n();
  const { reading, stars: n } = readCalibration(hub.error, hub.verdict);
  if (reading === "unproven") return <span className="status">{t("finder.cal.unproven")}</span>;
  return (
    <span className={`status ${reading === "over" ? "no" : "ok"}`}>
      {t(`finder.cal.${reading}` as Key, { stars: stars(n, intl) })}
    </span>
  );
}

/** One hub, as five plain lines and a button. */
function Row({ hub, onPick }: { hub: DirectoryHub; onPick: (hub: string) => void }) {
  const { t } = useI18n();
  const admission = hub.admission && ADMISSIONS.includes(hub.admission) ? hub.admission : "";
  return (
    <li className="finder-row">
      <div className="stack tight">
        <h3>{hub.name || hub.hub}</h3>
        <p className="muted">{hub.description || t("finder.unknownDescription")}</p>
        <p className="finder-facts">
          <span className={`status ${hub.accepting ? "ok" : "no"}`}>
            {t(hub.accepting ? "finder.accepting" : "finder.closed")}
          </span>
          {admission && <span className="muted">{t(`finder.admission.${admission}` as Key)}</span>}
          {hub.entities !== undefined && <span className="muted">{t("finder.entities", { n: hub.entities })}</span>}
        </p>
        <p className="finder-facts">
          <span className="eyebrow">{t("finder.cal.label")}</span>
          <Calibration hub={hub} />
          <span className="muted">{t("finder.cal.evidence", { n: hub.evidence })}</span>
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

  useEffect(() => {
    let live = true;
    api
      .directory()
      .then((d) => live && setHubs(d.hubs))
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
      {hubs === null ? (
        <p className="muted">{t("finder.loading")}</p>
      ) : (
        <ul className="finder-list">
          {hubs.map((h) => (
            <Row key={h.hub} hub={h} onPick={choose} />
          ))}
        </ul>
      )}
      <p className="muted small">{t("finder.cal.explain")}</p>
    </section>
  );
}
