import type { ReactNode, RefObject } from "react";
import { useI18n } from "../i18n";
import type { Key } from "../i18n/en";
import Display from "./Display";

// The page tells one story in three chapters: the traveller's agent, the same agent for any business, then the
// business's side. Each chapter has an anchor the header jumps to.

export type ChapterId = "travel" | "ask" | "business";
export const CHAPTERS: ChapterId[] = ["travel", "ask", "business"];

export default function Chapter({
  id,
  heading,
  lead,
  sectionRef,
  children,
}: {
  id: ChapterId;
  heading: Key;
  lead: string;
  sectionRef?: RefObject<HTMLElement>;
  children: ReactNode;
}) {
  const { t } = useI18n();
  const n = String(CHAPTERS.indexOf(id) + 1).padStart(2, "0");
  return (
    <section id={id} className="chapter" ref={sectionRef} aria-labelledby={`${id}-title`}>
      <div className="section-head">
        <span className="eyebrow">
          <span className="num">{n}</span> · {t(`chapter.${id}` as Key)}
        </span>
        <h2 id={`${id}-title`}>
          <Display text={t(heading)} />
        </h2>
        <p className="lead">{lead}</p>
      </div>
      {children}
    </section>
  );
}
