import { useCallback, useEffect, useRef, useState } from "react";
import { api, type ActivityEvent } from "../api";
import { useI18n } from "../i18n";
import type { Key } from "../i18n/en";

// The hub's step log. It starts with the page, so Details never has to wait for it, and a click
// refreshes it in parallel with the chat.

const POLL_MS = 2500;
const KEEP = 8;

/** Poll the hub log for as long as the page is open. `pull` forces one read, for a Details click. */
export function useActivityLog() {
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const last = useRef(0);
  const pull = useCallback(async () => {
    try {
      const feed = await api.activity(last.current);
      if (feed.last < last.current) setEvents(feed.events.slice(-KEEP));
      else {
        const fresh = feed.events.filter((e) => e.n > last.current);
        if (fresh.length) setEvents((old) => [...old, ...fresh].slice(-KEEP));
      }
      last.current = feed.last;
    } catch {
      /* the lines already on screen stay */
    }
  }, []);
  useEffect(() => {
    void pull();
    const timer = setInterval(() => void pull(), POLL_MS);
    return () => clearInterval(timer);
  }, [pull]);
  return { events, pull };
}

export default function JourneyLog({ events }: { events: ActivityEvent[] }) {
  const { t } = useI18n();
  if (!events.length) return null;
  const newest = [...events].reverse();
  return (
    <section className="journey-log" aria-label={t("card.log")}>
      <span className="eyebrow">{t("card.log")}</span>
      <ol>
        {newest.map((event) => (
          <li key={event.n}>
            <span>{t(`activity.agent.${event.agent}` as Key)}</span>
            <span>{t(`activity.step.${event.step}` as Key)}</span>
            {event.business && <span className="dim">{event.business}</span>}
            {event.outcome && (
              <span className={`activity-outcome ${event.outcome}`}>
                {t(`activity.outcome.${event.outcome}` as Key, { n: event.count ?? 0 })}
              </span>
            )}
          </li>
        ))}
      </ol>
    </section>
  );
}
