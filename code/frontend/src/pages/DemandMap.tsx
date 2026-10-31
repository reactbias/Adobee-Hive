import { useEffect, useState } from "react";
import { api, type DemandMap as Demand } from "../api";
import { useI18n } from "../i18n";

// The twist: agents' unmet requests tell a city's small businesses what to become.
export default function DemandMap() {
  const { t } = useI18n();
  const [demand, setDemand] = useState<Demand | null>(null);
  const [busy, setBusy] = useState(false);
  const [simulated, setSimulated] = useState(0);

  useEffect(() => {
    api.demand().then(setDemand);
  }, []);

  async function simulate() {
    setBusy(true);
    setDemand(await api.simulate(40));
    setSimulated((n) => n + 40);
    setBusy(false);
  }

  const max = Math.max(1, ...(demand?.features.map((f) => f.asked) ?? []));
  return (
    <div className="stack loose">
      <header className="page-head">
        <span className="eyebrow">{t("demand.eyebrow")}</span>
        <h1>{t("demand.title")}</h1>
        <p className="lead">{t("demand.lead")}</p>
        <div className="row">
          <button onClick={simulate} disabled={busy}>
            {t("demand.simulate")}
          </button>
          {simulated > 0 && <span className="muted">{t("demand.simulated", { n: simulated })}</span>}
        </div>
      </header>

      {demand && (
        <>
          <dl className="kpis">
            <div>
              <dd className="num">{demand.searches}</dd>
              <dt>{t("demand.kpi.searches", { days: demand.days })}</dt>
            </div>
            <div>
              <dd className="num">{demand.unserved_searches}</dd>
              <dt>{t("demand.kpi.unserved")}</dt>
            </div>
            <div>
              <dd>{demand.features[0]?.feature ?? "–"}</dd>
              <dt>{t("demand.kpi.top")}</dt>
            </div>
          </dl>

          <section className="stack">
            <div className="spread">
              <h3>{t("demand.chart.title")}</h3>
              <span className="legend muted">
                <i className="asked" /> {t("demand.legend.asked")} <i className="unserved" />{" "}
                {t("demand.legend.unserved")}
              </span>
            </div>
            {demand.features.length === 0 ? (
              <p className="muted">{t("demand.empty")}</p>
            ) : (
              <ul className="rows compact bars">
                {demand.features.map((f) => (
                  <li key={f.feature}>
                    <span className="bar-label">{f.feature}</span>
                    <span className="bar-track">
                      <span className="asked" style={{ width: `${(f.asked / max) * 100}%` }} />
                      <span className="unserved" style={{ width: `${(f.unserved / max) * 100}%` }} />
                    </span>
                    <span className="bar-value num muted">
                      {t("demand.ofAsked", { unserved: f.unserved, asked: f.asked })}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  );
}
