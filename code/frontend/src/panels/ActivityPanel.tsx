import { useEffect, useRef, useState } from "react";
import { api, type ActivityEvent } from "../api";
import Display from "../components/Display";
import { useI18n } from "../i18n";
import type { Key } from "../i18n/en";

// Presenter tools: what the agents do behind the scenes, live. The backend keeps one line per step (no person, no
// question text); this panel polls for new lines and shows the newest first, each run as one group.

const POLL_MS = 2500;
const KEEP = 200;

export default function ActivityPanel() {
  const { t, locale } = useI18n();
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [down, setDown] = useState(false);
  const last = useRef(0);
  const section = useRef<HTMLElement>(null);

  // A shared link (?demo#activity) lands here: the section renders after the browser looked for the anchor.
  useEffect(() => {
    if (window.location.hash === "#activity") section.current?.scrollIntoView?.();
  }, []);

  useEffect(() => {
    let stop = false;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      if (typeof document === "undefined" || !document.hidden) {
        try {
          const feed = await api.activity(last.current);
          if (stop) return;
          if (feed.last < last.current)
            setEvents(feed.events); // the Hive was reset: start over
          else {
            const fresh = feed.events.filter((e) => e.n > last.current);
            if (fresh.length) setEvents((old) => [...old, ...fresh].slice(-KEEP));
          }
          last.current = feed.last;
          setDown(false);
        } catch {
          if (!stop) setDown(true);
        }
        if (!stop) setLoaded(true);
      }
      if (!stop) timer = setTimeout(poll, POLL_MS);
    };
    poll();
    return () => {
      stop = true;
      clearTimeout(timer);
    };
  }, []);

  const time = new Intl.DateTimeFormat(locale, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hourCycle: "h23",
  });
  const newest = [...events].reverse();
  return (
    <section id="activity" className="chapter" ref={section} aria-labelledby="activity-title">
      <div className="chapter-grid">
        <div className="brief">
          <div className="page-head">
            <span className="eyebrow">{t("activity.eyebrow")}</span>
            <h2 id="activity-title">
              <Display text={t("activity.title")} />
            </h2>
            <p className="lead">{t("activity.lead")}</p>
          </div>
          <dl className="activity-legend">
            {(["partner", "web"] as const).map((s) => (
              <div key={s}>
                <dt>
                  <span className={`activity-source ${s}`}>{t(`activity.source.${s}`)}</span>
                </dt>
                <dd className="muted">{t(`activity.legend.${s}` as Key)}</dd>
              </div>
            ))}
          </dl>
        </div>
        <div className="frame">
          <div className="frame-head">
            <span className={`status ${down ? "no" : "ok"}`}>{down ? t("nav.down") : t("activity.live")}</span>
          </div>
          <div className="frame-body">
            {loaded && !events.length && !down && <p className="muted">{t("activity.empty")}</p>}
            <ol className="activity-feed" aria-live="polite">
              {newest.map((e, i) => (
                <li key={e.n} className={i > 0 && newest[i - 1].run !== e.run ? "activity-run" : undefined}>
                  <time className="num muted" dateTime={e.at}>
                    {time.format(new Date(e.at))}
                  </time>
                  <span className="activity-agent">{t(`activity.agent.${e.agent}` as Key)}</span>
                  <span className="activity-what">
                    <span className="activity-step">
                      {t(`activity.step.${e.step}` as Key)}
                      {e.business && <b> · {e.business}</b>}
                    </span>
                    {e.outcome && (
                      <span className={`activity-outcome ${e.outcome}`}>
                        {t(`activity.outcome.${e.outcome}` as Key, { n: e.count ?? 0 })}
                      </span>
                    )}
                  </span>
                  {e.source && (
                    <span className={`activity-source ${e.source}`}>{t(`activity.source.${e.source}`)}</span>
                  )}
                </li>
              ))}
            </ol>
          </div>
        </div>
      </div>
    </section>
  );
}
