import { useEffect, useState } from "react";
import { api, type DemandMap as Demand } from "../api";

// The twist: agents' unmet requests tell a city's small businesses what to become.
export default function DemandMap() {
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
    <div className="stack">
      <h1>What Basel's agents asked for</h1>
      <p className="lead">
        Every search an agent runs leaves a trace. When no business can serve it, that is not a lost booking, it is a
        business plan. Agents write it; local owners read it.
      </p>
      <div className="row">
        <button onClick={simulate} disabled={busy}>
          Simulate 40 traveller searches
        </button>
        {simulated > 0 && (
          <span className="muted">
            {simulated} simulated searches added. They run the real discovery code; only the travellers are made up.
          </span>
        )}
      </div>
      {demand && (
        <>
          <div className="grid three">
            <div className="panel">
              <h2>{demand.searches}</h2>
              <div className="muted">agent searches, last {demand.days} days</div>
            </div>
            <div className="panel">
              <h2>{demand.unserved_searches}</h2>
              <div className="muted">found no business at all</div>
            </div>
            <div className="panel">
              <h2>{demand.features[0]?.feature ?? "none yet"}</h2>
              <div className="muted">most unserved request</div>
            </div>
          </div>
          <section className="panel stack">
            <h3>Requested features: asked vs. nobody could serve</h3>
            {demand.features.length === 0 && (
              <p className="muted">No searches yet. Run the traveller agent or simulate some traffic.</p>
            )}
            {demand.features.map((f) => (
              <div key={f.feature} className="row" style={{ flexWrap: "nowrap" }}>
                <span style={{ width: 140, flexShrink: 0 }}>{f.feature}</span>
                <div style={{ flex: 1, position: "relative", height: 22 }}>
                  <div
                    style={{
                      position: "absolute",
                      inset: 0,
                      width: `${(f.asked / max) * 100}%`,
                      background: "var(--honey-soft)",
                      border: "1px solid #f0d77a",
                      borderRadius: 6,
                    }}
                  />
                  <div
                    style={{
                      position: "absolute",
                      inset: 0,
                      width: `${(f.unserved / max) * 100}%`,
                      background: "var(--honey)",
                      border: "1px solid var(--ink)",
                      borderRadius: 6,
                    }}
                  />
                </div>
                <span className="muted" style={{ width: 150, flexShrink: 0, textAlign: "right" }}>
                  {f.unserved} of {f.asked} unserved
                </span>
              </div>
            ))}
            <p className="muted">
              Dark bar: searches with this request where no business matched all constraints. Light bar: all searches
              asking for it.
            </p>
          </section>
        </>
      )}
    </div>
  );
}
