import { useMemo, useState } from "react";
import GroupChat, { type Segment } from "../components/GroupChat";
import { useI18n } from "../i18n";
import type { Step } from "../api";

const HIRING_HUB_URL = (import.meta.env.VITE_HIRING_HUB_URL ?? "http://localhost:3000").replace(/\/$/, "");
const POSITION_ID = Number(import.meta.env.VITE_HIRING_HUB_POSITION_ID ?? 1);

const step = (...args: [string, Step["input"], Step["output"]]): Step => {
  const [tool, input, output] = args;
  return { tool, input, output };
};

export default function HRPanel() {
  const { t } = useI18n();
  const [title, setTitle] = useState("Python Engineer");
  const [description, setDescription] = useState("Build hiring tools for a growing product team in Basel.");
  const [started, setStarted] = useState(false);
  const [handoff, setHandoff] = useState(false);

  const segments = useMemo<Segment[]>(() => {
    if (!started) return [];
    const steps: Step[] = [
      step("hr_create_job", { title, description }, { id: POSITION_ID, title }),
      step(
        "hr_find_people",
        { skills: ["python", "product design"], location: "Basel" },
        {
          matches: [{ id: "anouk-pfister", name: "Anouk Pfister", matched: ["python"], signature_valid: true }],
          excluded: [],
        },
      ),
      step("hub_connect", { entity_id: "anouk-pfister" }, { state: "open", folder_link: "fl-demo" }),
      step("hr_grant_cv", { path: "cv.pdf" }, { path: "cv.pdf", visibility: "public-summary" }),
      step("hr_submit_cv", { position_id: POSITION_ID, path: "cv.pdf" }, { status: "queued", filename: "cv.pdf" }),
    ];
    return [
      { kind: "guest", text: `${title}: ${description}` },
      { kind: "ack" },
      { kind: "steps", steps },
      { kind: "agent", text: t("hr.chat.summary") },
      { kind: "consent", handoff: true },
    ];
  }, [description, started, t, title]);

  const openHiringHub = () => {
    setHandoff(true);
    window.open(`${HIRING_HUB_URL}/positions/${POSITION_ID}`, "_blank", "noopener,noreferrer");
  };

  return (
    <section className="screen-find journey">
      <div className="journey-brief">
        <p className="eyebrow">{t("hr.eyebrow")}</p>
        <h1>{t("hr.title")}</h1>
        <p className="lead">{t("hr.lead")}</p>
        <form
          className="brief-form"
          onSubmit={(event) => {
            event.preventDefault();
            setHandoff(false);
            setStarted(true);
          }}
        >
          <label>
            {t("hr.job.title")}
            <input value={title} onChange={(event) => setTitle(event.target.value)} />
          </label>
          <label>
            {t("hr.job.description")}
            <textarea value={description} onChange={(event) => setDescription(event.target.value)} rows={4} />
          </label>
          <button className="primary" type="submit">
            {t("hr.start")}
          </button>
        </form>
      </div>
      <div className="journey-stage">
        <GroupChat
          segments={segments}
          guestName={t("hr.chat.recruiter")}
          pending={false}
          full
          meta={<span>{t("hr.meta")}</span>}
          pinned={
            started ? (
              <div className="agent-gate">
                <p className="eyebrow">{t("hr.handoff.eyebrow")}</p>
                <h3>{t("hr.handoff.title")}</h3>
                <p>{t("hr.handoff.body")}</p>
                <button className="primary" onClick={openHiringHub}>
                  {t("hr.handoff.open")}
                </button>
                {handoff && <p className="status ok">{t("hr.handoff.sent")}</p>}
              </div>
            ) : undefined
          }
        />
      </div>
    </section>
  );
}
