import { forwardRef } from "react";
import { useI18n } from "../i18n";
import type { Key } from "../i18n/en";
import AskPanel from "../panels/AskPanel";
import CardPanel from "../panels/CardPanel";
import DemandPanel from "../panels/DemandPanel";
import OwnerPanel from "../panels/OwnerPanel";
import Display from "./Display";

// Under the chat, the rest of the Hive on the same page: the card the agent read, the owner who wrote it, what the
// city asked for, and the other businesses. Switching tabs is looking, never deciding: nothing here books.

export type Door = "card" | "owner" | "city" | "ask";
const DOORS: [Door, Key][] = [
  ["card", "door.tab.card"],
  ["owner", "door.tab.owner"],
  ["city", "door.tab.city"],
  ["ask", "door.tab.ask"],
];

interface Props {
  door: Door;
  onDoor: (d: Door) => void;
  /** The card on the card tab, by slug. */
  slug: string;
  onSlug: (slug: string) => void;
  /** The business the owner tab opens on: the one just booked, if any. */
  ownerCard: string;
}

const BehindTheDoor = forwardRef<HTMLElement, Props>(function BehindTheDoor(props, ref) {
  const { t } = useI18n();
  return (
    <section className="door" ref={ref} aria-labelledby="door-title">
      <div className="section-head">
        <span className="eyebrow">{t("door.eyebrow")}</span>
        <h2 id="door-title">
          <Display text={t("door.title")} />
        </h2>
        <p className="lead">{t("door.lead")}</p>
      </div>
      <div className="door-tabs" role="tablist" aria-labelledby="door-title">
        {DOORS.map(([d, label]) => (
          <button
            key={d}
            role="tab"
            id={`door-${d}`}
            aria-selected={props.door === d}
            aria-controls="door-panel"
            className={props.door === d ? "on" : ""}
            onClick={() => props.onDoor(d)}
          >
            {t(label)}
          </button>
        ))}
      </div>
      <div className="door-panel" role="tabpanel" id="door-panel" aria-labelledby={`door-${props.door}`}>
        {props.door === "card" && <CardPanel slug={props.slug} onSlug={props.onSlug} />}
        {props.door === "owner" && <OwnerPanel initial={props.ownerCard} />}
        {props.door === "city" && <DemandPanel />}
        {props.door === "ask" && <AskPanel />}
      </div>
    </section>
  );
});

export default BehindTheDoor;
