import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Card, type Job, type Profile } from "../api";

// Demo user. Real accounts and OAuth connectors come after the hackathon.
const ME = "tobi";
const FIELDS: (keyof Profile)[] = ["headline", "skills", "about", "location", "projects"];

export default function ApplicantDashboard() {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [connectors, setConnectors] = useState<Record<string, { label: string; description: string }>>({});
  const [jobs, setJobs] = useState<Job[]>([]);
  const [pitch, setPitch] = useState<{ job: string; message: string; shared: string[] } | null>(null);
  const [card, setCard] = useState<Card | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.profile(ME).then(setProfile);
    api.connectors().then(setConnectors);
    api.jobs().then(setJobs);
  }, []);

  if (!profile) return <p className="muted">Loading...</p>;
  const update = (patch: Partial<Profile>) => setProfile({ ...profile, ...patch });
  const save = async () => setProfile(await api.saveProfile(ME, profile));

  async function makePitch(job: Job) {
    setBusy(true);
    await api.saveProfile(ME, profile!);
    const out = await api.pitch(ME, job.id);
    setPitch({ job: job.title, message: out.message, shared: out.shared_fields });
    setBusy(false);
  }

  return (
    <div className="stack">
      <h1>My persona</h1>
      <p className="muted">
        No CV. You own one living profile, fed by your tools, and decide field by field what your agent may share.
        Publish it and you become a signed person card in the Hive that company agents can find.
      </p>
      <div className="grid two">
        <section className="panel stack">
          <h3>Connect your sources</h3>
          {Object.entries(connectors).map(([key, c]) => (
            <div key={key} className="row" style={{ justifyContent: "space-between" }}>
              <div><strong>{c.label}</strong><div className="muted">{c.description}</div></div>
              {profile.connectors[key]?.connected
                ? <span className="chip ok">connected</span>
                : <button className="ghost" onClick={async () => setProfile(await api.connect(ME, key))}>Connect</button>}
            </div>
          ))}
          <p className="muted">Connectors are simulated imports in this prototype.</p>
        </section>

        <section className="panel stack">
          <h3>Profile</h3>
          <div><label>Name</label><input value={profile.display_name} onChange={(e) => update({ display_name: e.target.value })} /></div>
          <div><label>Headline</label><input value={profile.headline} onChange={(e) => update({ headline: e.target.value })} /></div>
          <div><label>About</label><textarea value={profile.about} onChange={(e) => update({ about: e.target.value })} /></div>
          <div><label>Looking for</label><input value={profile.looking_for} onChange={(e) => update({ looking_for: e.target.value })} /></div>
          <div><label>Skills (comma separated)</label><input value={profile.skills.join(", ")} onChange={(e) => update({ skills: e.target.value.split(",").map((s) => s.trim()).filter(Boolean) })} /></div>
          <div>
            <label>Contact format</label>
            <select value={profile.contact_format} onChange={(e) => update({ contact_format: e.target.value })}>
              <option>agent first</option><option>email</option><option>call</option>
            </select>
          </div>
          <label>What my agent may share</label>
          <div className="row">
            {FIELDS.map((f) => (
              <label key={f} className="chip" style={{ cursor: "pointer" }}>
                <input type="checkbox" style={{ width: "auto", marginRight: 6 }} checked={profile.visibility[f] ?? false}
                  onChange={(e) => update({ visibility: { ...profile.visibility, [f]: e.target.checked } })} />
                {f}
              </label>
            ))}
          </div>
          <div className="row">
            <button onClick={save}>Save</button>
            <button className="ghost" onClick={async () => { await save(); setCard(await api.publishProfile(ME)); }}>Publish to the Hive</button>
          </div>
          {card && <p className="muted">Published as signed card <Link to={`/card/${card.slug}`}>{card.slug}</Link>, version {card.version}.</p>}
        </section>
      </div>

      <section className="panel stack">
        <h3>How my agent would pitch me</h3>
        <div className="row">
          {jobs.map((j) => <button key={j.id} className="ghost" disabled={busy} onClick={() => makePitch(j)}>{j.title}</button>)}
        </div>
        {pitch && (
          <>
            <div className="bubble assistant">{pitch.message}</div>
            <p className="muted">Shared with the company agent: {pitch.shared.join(", ")}</p>
          </>
        )}
      </section>
    </div>
  );
}
