import { useMemo, useState } from "react";
import GroupChat, { type Segment } from "../components/GroupChat";
import { useI18n } from "../i18n";
import type { Step } from "../api";

// A script of the hiring flow, labelled as one: it calls none of the hr_* tools, so it must not say a job
// was created or a CV sent. The tools themselves are real and need a link secret and the organisation's key.

const POSITION_ID = 1;

const step = (tool: string, input: Step["input"], output: Step["output"]): Step => ({ tool, input, output });

/** The same tools and order as a real run, with made-up answers. */
const CREATE = (title: string, description: string) => [
  step("hr_create_job", { title, description }, { id: POSITION_ID, title }),
];
const FIND = [
  step(
    "hr_find_people",
    { skills: ["python", "product design"], location: "Basel" },
    { matches: [{ id: "anouk-pfister", name: "Anouk Pfister", matched: ["python"] }], excluded: [] },
  ),
  step("hub_connect", { entity_id: "anouk-pfister" }, { state: "requested", folder_link: "fl-demo" }),
];
const CANDIDATE = [
  step("hr_decide_intro", { connection_id: "cx-demo", approve: true }, { state: "open" }),
  step("hr_grant_cv", { path: "cv.pdf" }, { path: "cv.pdf", to: "hiring-agent" }),
];
const SUBMIT = [
  step("hr_submit_cv", { position_id: POSITION_ID, path: "cv.pdf" }, { position_id: POSITION_ID, path: "cv.pdf" }),
];

export default function HRPanel() {
  const { t } = useI18n();
  // Unedited fields stay null, so the suggested text follows the language switch.
  const [title, setTitle] = useState<string | null>(null);
  const [description, setDescription] = useState<string | null>(null);
  const [brief, setBrief] = useState<{ title: string; description: string } | null>(null);
  const shownTitle = title ?? t("hr.default.title");
  const shownDescription = description ?? t("hr.default.description");
  const hiringHub = (import.meta.env.VITE_HIRING_HUB_URL ?? "").replace(/\/$/, "");

  const segments = useMemo<Segment[]>(() => {
    if (!brief) return [];
    const hub = { name: t("hr.speaker.hub"), role: t("hr.speaker.hubRole") };
    const hive = { name: t("chat.name.hive"), role: t("chat.role.hive") };
    const candidate = { name: t("hr.speaker.candidate"), role: t("hr.speaker.candidateRole") };
    return [
      { kind: "guest", text: `${brief.title}: ${brief.description}` },
      { kind: "ack" },
      { kind: "steps", steps: CREATE(brief.title, brief.description), speaker: hub },
      { kind: "steps", steps: FIND, speaker: hive },
      { kind: "steps", steps: CANDIDATE, speaker: candidate },
      { kind: "steps", steps: SUBMIT, speaker: hub },
      { kind: "agent", text: t("hr.chat.summary") },
    ];
  }, [brief, t]);

  return (
    <section id="hr" className="screen screen-find" aria-labelledby="hr-title">
      <div className="screen-head">
        <p className="eyebrow">{t("hr.eyebrow")}</p>
        <h1 id="hr-title">{t("hr.title")}</h1>
        <p className="lead">{t("hr.lead")}</p>
      </div>
      {!brief && (
        <form
          className="hr-brief"
          onSubmit={(event) => {
            event.preventDefault();
            setBrief({ title: shownTitle, description: shownDescription });
          }}
        >
          <div>
            <label htmlFor="hr-job-title">{t("hr.job.title")}</label>
            <input id="hr-job-title" value={shownTitle} onChange={(event) => setTitle(event.target.value)} />
          </div>
          <div>
            <label htmlFor="hr-job-description">{t("hr.job.description")}</label>
            <textarea
              id="hr-job-description"
              value={shownDescription}
              onChange={(event) => setDescription(event.target.value)}
              rows={4}
            />
          </div>
          <button className="primary" type="submit">
            {t("hr.start")}
          </button>
        </form>
      )}
      {brief && (
        <div className="journey">
          <GroupChat
            segments={segments}
            guestName={t("hr.chat.recruiter")}
            pending={false}
            meta={
              <>
                <button className="quiet" onClick={() => setBrief(null)}>
                  {t("hr.change")}
                </button>
                <span className="stage-meta">{t("hr.meta")}</span>
              </>
            }
            pinned={
              hiringHub ? (
                <div className="gate">
                  <p className="eyebrow">{t("hr.handoff.eyebrow")}</p>
                  <h3>{t("hr.handoff.title")}</h3>
                  <p>{t("hr.handoff.body")}</p>
                  <a className="btn ghost arrow" href={hiringHub} target="_blank" rel="noopener noreferrer">
                    {t("hr.handoff.open")}
                  </a>
                </div>
              ) : undefined
            }
          />
        </div>
      )}
    </section>
  );
}
