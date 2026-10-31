import type { ReactNode, RefObject } from "react";
import { useI18n } from "../i18n";
import type { Key } from "../i18n/en";
import Display from "./Display";

// One journey: Search, then Opportunities. Every
// chapter has the same shape: a brief on paper (heading, lead, the input) beside one panel of the screen's height,
// where everything generated appears and scrolls inside, so the page never grows with it.

export type ChapterId = "travel" | "business";
export const CHAPTERS: ChapterId[] = ["travel", "business"];

export default function Chapter({
  id,
  heading,
  lead,
  eyebrow,
  headingLevel = 2,
  side,
  sectionRef,
  stack = false,
  children,
}: {
  id: ChapterId;
  heading: Key;
  lead: string;
  /** Replaces the numbered chapter name above the heading. */
  eyebrow?: string;
  /** The first chapter carries the page's h1. */
  headingLevel?: 1 | 2;
  /** The brief's working part, under the lead: the input, the switches. */
  side?: ReactNode;
  sectionRef?: RefObject<HTMLElement>;
  /** Search across the top, and what it draws underneath, instead of a brief beside a panel. */
  stack?: boolean;
  /** The panel: one `.frame` element. */
  children: ReactNode;
}) {
  const { t } = useI18n();
  const n = String(CHAPTERS.indexOf(id) + 1).padStart(2, "0");
  const H = headingLevel === 1 ? "h1" : "h2";
  const head = (
    <div className="page-head">
      <span className="eyebrow">
        {eyebrow ?? (
          <>
            <span className="num">{n}</span> · {t(`chapter.${id}` as Key)}
          </>
        )}
      </span>
      <H id={`${id}-title`}>
        <Display text={t(heading)} />
      </H>
      <p className="lead">{lead}</p>
    </div>
  );
  if (stack) {
    return (
      <section id={id} className="chapter stack" ref={sectionRef} aria-labelledby={`${id}-title`}>
        {head}
        {side}
        {children}
      </section>
    );
  }
  return (
    <section id={id} className="chapter" ref={sectionRef} aria-labelledby={`${id}-title`}>
      <div className="chapter-grid">
        <div className="brief">
          {head}
          {side}
        </div>
        {children}
      </div>
    </section>
  );
}

/** The light panel beside the brief: a fixed height, an optional header, and a body that scrolls inside. */
export function Frame({
  label,
  head,
  bodyRef,
  children,
}: {
  label: string;
  head?: ReactNode;
  bodyRef?: RefObject<HTMLDivElement>;
  children: ReactNode;
}) {
  return (
    <section className="frame" aria-label={label}>
      {head && <div className="frame-head">{head}</div>}
      <div className="frame-body" ref={bodyRef}>
        {children}
      </div>
    </section>
  );
}
