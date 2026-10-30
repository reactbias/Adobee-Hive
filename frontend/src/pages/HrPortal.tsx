import { useEffect, useState } from "react";
import { api, type Candidate, type Job, type QueryResult } from "../api";

const STAGES = ["received", "screened", "shortlisted", "interview", "offer", "rejected"];
const QUESTIONS = [
  "Python developers in Basel with 3+ years",
  "Designers who know Figma and speak German, most experienced first",
  "How many candidates per seniority level are shortlisted?",
];

export default function HrPortal() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [jobId, setJobId] = useState("");
  const [funnel, setFunnel] = useState<{ stage: string; count: number }[]>([]);
  const [question, setQuestion] = useState(QUESTIONS[0]);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [selected, setSelected] = useState<Candidate | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refresh = () => api.funnel(jobId || undefined).then(setFunnel);
  useEffect(() => { api.jobs().then(setJobs); }, []);
  useEffect(() => { refresh(); }, [jobId]);

  async function ask() {
    setBusy(true);
    setError("");
    try {
      setResult(await api.query(question));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function upload(files: FileList | null) {
    if (!files?.length) return;
    setBusy(true);
    try {
      const out = await api.uploadCvs(Array.from(files), jobId || undefined);
      const failed = out.filter((r) => "error" in r);
      setError(failed.length ? `${failed.length} file(s) failed to parse` : "");
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  async function setStage(stage: string) {
    if (!selected) return;
    setSelected(await api.setStage(selected.id, stage));
    refresh();
  }

  const max = Math.max(1, ...funnel.map((f) => f.count));
  return (
    <div className="stack">
      <h1>HR portal</h1>
      <p className="muted">
        The same Hive, the other way round: a company's agent looking for people. CVs are parsed into a database;
        recruiters ask in plain language. The model sees the schema and the question, never candidate data.
      </p>
      {error && <p className="error">{error}</p>}
      <div className="grid two">
        <section className="panel stack">
          <div className="row">
            <select value={jobId} onChange={(e) => setJobId(e.target.value)} style={{ flex: 1 }}>
              <option value="">All jobs</option>
              {jobs.map((j) => <option key={j.id} value={j.id}>{j.title}</option>)}
            </select>
            <label className="btn" style={{ margin: 0 }}>
              Upload CVs
              <input type="file" multiple accept=".pdf,.txt,.md" hidden onChange={(e) => upload(e.target.files)} />
            </label>
          </div>
          <h3>Funnel</h3>
          <div className="funnel">
            {funnel.map((f) => (
              <div key={f.stage} className="row">
                <span style={{ width: 90 }} className="muted">{f.stage}</span>
                <span className="bar" style={{ width: `${(f.count / max) * 70}%` }}>{f.count}</span>
              </div>
            ))}
          </div>
        </section>
        <section className="panel stack">
          <h3>Ask anything</h3>
          <textarea value={question} onChange={(e) => setQuestion(e.target.value)} />
          <div className="row">
            <button onClick={ask} disabled={busy}>Ask</button>
            {QUESTIONS.map((q) => (
              <button key={q} className="ghost" style={{ fontSize: "0.78rem", fontWeight: 400 }} onClick={() => setQuestion(q)}>{q}</button>
            ))}
          </div>
          {result && (
            <>
              <p className="muted">{result.explanation}</p>
              <details><summary className="muted">SQL ({result.mode})</summary><pre>{result.sql}</pre></details>
            </>
          )}
        </section>
      </div>

      {result && (
        <section className="panel">
          <table>
            <thead><tr>{result.columns.filter((c) => c !== "id").map((c) => <th key={c}>{c.replace("_", " ")}</th>)}</tr></thead>
            <tbody>
              {result.rows.map((r, i) => (
                <tr key={i} className={r.id ? "clickable" : ""} onClick={() => r.id && api.candidate(String(r.id)).then(setSelected)}>
                  {result.columns.filter((c) => c !== "id").map((c) => (
                    <td key={c}>{Array.isArray(r[c]) ? (r[c] as string[]).map((s) => <span key={s} className="chip">{s}</span>) : String(r[c] ?? "")}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {result.rows.length === 0 && <p className="muted">No rows.</p>}
        </section>
      )}

      {selected && (
        <section className="panel stack">
          <div className="row">
            <h3 style={{ marginRight: "auto" }}>{selected.full_name}</h3>
            <select value={selected.stage} onChange={(e) => setStage(e.target.value)} style={{ width: 160 }}>
              {STAGES.map((s) => <option key={s}>{s}</option>)}
            </select>
            <button className="ghost" onClick={() => setSelected(null)}>Close</button>
          </div>
          <div className="muted">{selected.headline} · {selected.location} · {selected.years_experience} years</div>
          <p>{selected.summary}</p>
          <div>{selected.skills.map((s) => <span key={s} className="chip">{s}</span>)}</div>
          {selected.experiences?.map((x, i) => (
            <div key={i}><strong>{x.role}</strong>, {x.company} ({x.start_year} to {x.end_year ?? "now"})</div>
          ))}
        </section>
      )}
    </div>
  );
}
