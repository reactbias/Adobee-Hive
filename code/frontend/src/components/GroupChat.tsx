import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import type { AskResult, Booking, Critic, Handoff, SecondOpinion, Step } from "../api";
import { AskCard } from "./AskParts";
import { useI18n } from "../i18n";
import { delayFor, type Beat } from "../lib/pace";
import { demoMode } from "../lib/demo";
import { Ask, Reply, Withheld, genuine, namesFrom } from "./TraceParts";

// The traveller page as a group chat: people and agents in one conversation. Every message comes from real data,
// the guest's words, an MCP call or its answer. Playback paces the messages so a room can follow who is talking.

export type Who = "guest" | "agent" | "hive" | "business" | "critic" | "sceptic" | "mirror";

/** What happened, in order. The chat turns each segment into one or more messages. */
export type Segment =
  | { kind: "guest"; text: string }
  | { kind: "ack" }
  | { kind: "steps"; steps: Step[] }
  | { kind: "critic"; critic: Critic }
  | { kind: "opinion"; opinion: SecondOpinion }
  | { kind: "consensus"; agreed: boolean }
  | { kind: "agent"; text: string }
  | { kind: "consent" }
  | { kind: "receipt"; booking: Booking }
  | { kind: "next" }
  | { kind: "refused" }
  | { kind: "ask"; result: AskResult }
  | { kind: "handoff"; handoff: Handoff };

interface Msg {
  who: Who;
  name: string;
  role: string;
  to?: string;
  tool?: string;
  /** The source that answered, when it is not the configured Hive. */
  via?: string;
  ms?: number;
  badge?: ReactNode;
  body: ReactNode;
  consent?: boolean;
  beat: Beat;
  chars?: number;
}

const WHO: Who[] = ["guest", "agent", "hive", "business", "critic", "sceptic", "mirror"];
const AVATAR = Object.fromEntries(WHO.map((who) => [who, `${import.meta.env.BASE_URL}personas/${who}.svg`])) as Record<
  Who,
  string
>;

type Rec = Record<string, unknown>;

const reducedMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;

export function Avatar({ who, size = 40, live = false }: { who: Who; size?: number; live?: boolean }) {
  return (
    <span className={`avatar avatar-${who}${live ? " live" : ""}`} style={{ width: size, height: size }}>
      <img src={AVATAR[who]} alt="" width={size} height={size} />
    </span>
  );
}

export default function GroupChat({
  segments,
  guestName,
  pending,
  pinned,
  receipt,
  followUp,
  refused,
  meta,
}: {
  segments: Segment[];
  guestName: string;
  /** The request is still with the agent: show it typing. */
  pending: boolean;
  /** Shown under the conversation once playback has caught up: the approval question. */
  pinned?: ReactNode;
  /** The signed receipt card, attached to the business's confirmation. */
  receipt?: ReactNode;
  /** What the agent offers once the stay is booked. */
  followUp?: ReactNode;
  /** The listings the agent's guard refused this run, told by the agent itself. */
  refused?: ReactNode;
  meta: ReactNode;
}) {
  const { t } = useI18n();
  const scroller = useRef<HTMLDivElement>(null);
  const [shown, setShown] = useState(0);

  const messages = useMemo(() => {
    const all = segments.flatMap((s) => (s.kind === "steps" ? s.steps : []));
    const names = namesFrom(all);
    // With several sources, discovery names them all, the configured Hive first.
    const primary = all.find((s) => s.tool === "hive_discover" && s.source)?.source?.split(", ")[0];
    const hive = t("chat.name.hive");
    const guest = { who: "guest" as const, name: guestName, role: t("chat.role.guest") };
    const agent = { who: "agent" as const, name: t("chat.name.agent"), role: t("chat.role.agent") };
    const out: Msg[] = [];
    for (const seg of segments) {
      switch (seg.kind) {
        case "guest":
          out.push({ ...guest, beat: "first", body: <p>{seg.text}</p> });
          break;
        case "ack":
          out.push({ ...agent, beat: "say", chars: t("chat.agent.ack").length, body: <p>{t("chat.agent.ack")}</p> });
          break;
        case "agent":
          out.push({ ...agent, beat: "say", chars: seg.text.length, body: <p>{seg.text}</p> });
          break;
        case "consent":
          out.push({ ...guest, consent: true, beat: "instant", body: <p>{t("chat.guest.yes")}</p> });
          break;
        // Three agents talk it through before the guest is asked: the critic argues for the strongest alternative.
        case "critic": {
          const c = seg.critic;
          const critic = { who: "critic" as const, name: t("chat.name.critic"), role: t("chat.role.critic") };
          out.push({ ...critic, beat: "think", body: <p>{c.challenge}</p> });
          if (c.answer) out.push({ ...agent, to: critic.name, beat: "say", chars: 40, body: <p>{c.answer}</p> });
          out.push({
            ...critic,
            beat: "say",
            chars: c.note.length,
            body: (
              <p>
                <span className={`status ${c.verdict === "agree" ? "ok" : "no"}`}>
                  {t(c.verdict === "agree" ? "agent.opinion.agree" : "agent.opinion.concern")}
                </span>{" "}
                {c.note}
              </p>
            ),
          });
          break;
        }
        case "consensus": {
          const line = t(seg.agreed ? "chat.consensus.agree" : "chat.consensus.split");
          out.push({ ...agent, beat: "say", chars: 20, body: <p className="consensus">{line}</p> });
          break;
        }
        case "opinion": {
          const o = seg.opinion;
          out.push({
            who: "sceptic",
            name: t("chat.name.sceptic"),
            role: t("chat.role.sceptic", { by: o.by }) + (o.fallback ? ` (${o.fallback})` : ""),
            ms: o.ms,
            beat: "think",
            body: (
              <p>
                <span className={`status ${o.verdict === "agree" ? "ok" : "no"}`}>
                  {t(o.verdict === "agree" ? "agent.opinion.agree" : "agent.opinion.concern")}
                </span>{" "}
                {o.note}
              </p>
            ),
          });
          break;
        }
        case "receipt":
          out.push({
            who: "business",
            name: seg.booking.business,
            role: t("chat.role.business"),
            beat: "reply",
            body: receipt,
          });
          break;
        case "refused":
          if (refused) out.push({ ...agent, beat: "think", body: refused });
          break;
        // A question about any business: the Hive's cards answer, the critic names what was left out, the verifier
        // reports the signatures, and your agent sums up. All of it from the one explore_ask answer.
        case "ask": {
          const r = seg.result;
          const critic = { who: "critic" as const, name: t("chat.name.critic"), role: t("chat.role.critic") };
          out.push({
            ...agent,
            to: hive,
            tool: "explore_ask",
            beat: "think",
            body: <p>{t("chat.ask.call", { question: r.question })}</p>,
          });
          out.push({
            who: "hive",
            name: hive,
            role: t("chat.role.hive"),
            beat: "reply",
            body: <p>{r.replies.length ? t("chat.ask.found", { n: r.replies.length }) : t("ask.empty")}</p>,
          });
          for (const reply of r.replies)
            out.push({
              who: "business",
              name: reply.name,
              role: t("chat.role.card"),
              beat: "reply",
              badge: (
                <span className={`seal-badge ${!reply.signature_valid ? "no" : reply.claimed ? "ok" : "warm"}`}>
                  {!reply.signature_valid
                    ? t("trust.invalid")
                    : reply.claimed
                      ? t("trust.signed")
                      : t("trust.unclaimed")}
                </span>
              ),
              body: <AskCard reply={reply} />,
            });
          if (r.excluded.length)
            out.push({
              ...critic,
              beat: "think",
              body: (
                <>
                  <p>{t("ask.excluded")}</p>
                  <ul className="left-out">
                    {r.excluded.map((e) => (
                      <li key={e.card_id + e.item}>
                        {e.business}, {e.item}: {e.why_not.join("; ")}
                      </li>
                    ))}
                  </ul>
                </>
              ),
            });
          if (r.unserved) out.push({ ...critic, beat: "think", body: <p>{t("chat.ask.uncovered")}</p> });
          if (r.replies.length) {
            const signed = r.replies.filter((x) => x.signature_valid && x.claimed).length;
            const unclaimed = r.replies.filter((x) => x.signature_valid && !x.claimed).length;
            out.push({
              who: "sceptic",
              name: t("chat.name.sceptic"),
              role: t("chat.role.verifier"),
              beat: "think",
              body: <p>{t("chat.ask.checked", { n: r.replies.length, signed, unclaimed })}</p>,
            });
          }
          if (r.answer) out.push({ ...agent, beat: "say", chars: r.answer.length, body: <p>{r.answer}</p> });
          break;
        }
        case "handoff":
          out.push({
            ...agent,
            beat: "say",
            chars: 40,
            body: (
              <>
                <p>{t("ask.handoff", { business: seg.handoff.business })}</p>
                <a className="btn ghost arrow" href={seg.handoff.url} target="_blank" rel="noopener noreferrer">
                  {t("ask.continue", { action: seg.handoff.action })}
                </a>
              </>
            ),
          });
          break;
        case "next":
          if (followUp) out.push({ ...agent, beat: "say", chars: 60, body: followUp });
          break;
        case "steps":
          for (const step of seg.steps) {
            const id = String((step.input as Rec).card_id ?? "");
            const business = names[id] ?? String(step.output.business ?? step.output.name ?? hive);
            const sig = genuine(step);
            // Anything not from the configured Hive is a copy nobody vouches for: it speaks as the mirror.
            const foreign = Boolean(step.source && primary && step.source !== primary && step.tool !== "hive_discover");
            const speaker =
              step.tool === "hive_discover"
                ? { who: "hive" as const, name: hive, role: t("chat.role.hive") }
                : sig === false || foreign
                  ? { who: "mirror" as const, name: t("chat.name.mirror"), role: t("chat.role.mirror") }
                  : { who: "business" as const, name: business, role: t("chat.role.business") };
            out.push({
              ...agent,
              to: speaker.name,
              tool: step.tool,
              beat: "think",
              body: <Ask step={step} names={names} />,
            });
            out.push({
              ...speaker,
              ms: step.ms,
              beat: "reply",
              via: foreign ? step.source : undefined,
              badge:
                step.signature === "unchecked" ? (
                  <span className="seal-badge warm">{t("trace.sig.unchecked")}</span>
                ) : sig === null ? undefined : (
                  <span className={`seal-badge ${sig ? "ok" : "no"}`}>
                    <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden>
                      <path d="M12 2.8 19.8 7.3v9.4L12 21.2 4.2 16.7V7.3Z" />
                      {sig ? <path className="tick" d="M8.6 12.2l2.3 2.3 4.6-4.8" /> : <path d="M9 9l6 6M15 9l-6 6" />}
                    </svg>
                    {sig ? t("trace.sig.ok") : t("trace.sig.bad")}
                  </span>
                ),
              body: (
                <>
                  <Reply step={step} />
                  {step.guard && step.guard.length > 0 && <Withheld findings={step.guard} />}
                  {demoMode() && (
                    <details>
                      <summary>{t("trace.raw")}</summary>
                      <pre>{JSON.stringify({ input: step.input, output: step.output }, null, 2)}</pre>
                    </details>
                  )}
                </>
              ),
            });
          }
          break;
      }
    }
    return out;
  }, [segments, guestName, receipt, followUp, refused, t]);

  // New messages after an approval continue from where the chat was; a new trip starts over.
  useEffect(() => {
    if (shown > messages.length) setShown(messages.length);
  }, [shown, messages.length]);
  useEffect(() => {
    if (shown >= messages.length) return;
    const timer = setTimeout(() => setShown((n) => n + 1), delayFor(messages[shown].beat, messages[shown].chars));
    return () => clearTimeout(timer);
  }, [shown, messages.length]);

  const caughtUp = shown >= messages.length;
  const next = caughtUp ? (pending ? "agent" : null) : messages[shown].who;
  const nextName = caughtUp ? t("chat.name.agent") : messages[shown]?.name;
  // Before a call or a judgement an agent thinks; before a line of text anyone types.
  const presence = t(caughtUp || messages[shown].beat === "think" ? "chat.thinking" : "chat.typing");

  // Follow the conversation while the reader is at the bottom. Scrolling up to reread stops it, and a button
  // offers the way back; reaching the bottom again, or the guest speaking, resumes it.
  const follow = useRef(true);
  const lastTop = useRef(0);
  const [behind, setBehind] = useState(false);
  const toLatest = (smooth = true) => {
    const el = scroller.current;
    follow.current = true;
    setBehind(false);
    if (el) el.scrollTo({ top: el.scrollHeight, behavior: smooth && !reducedMotion() ? "smooth" : "auto" });
  };
  const onScroll = () => {
    const el = scroller.current;
    if (!el) return;
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 48) {
      follow.current = true;
      setBehind(false);
    } else if (el.scrollTop < lastTop.current - 2) follow.current = false;
    lastTop.current = el.scrollTop;
  };
  const last = segments[segments.length - 1];
  useEffect(() => {
    if (!last || last.kind === "guest") follow.current = true;
  }, [last]);
  useEffect(() => {
    if (follow.current) toLatest();
    else if (shown > 0) setBehind(true);
  }, [shown, next, caughtUp, pinned]);

  // On a phone or tablet the chat sits under the request: when the agents start talking, bring it into view.
  const stage = useRef<HTMLElement>(null);
  useEffect(() => {
    const el = stage.current;
    if (!pending || !el) return;
    const r = el.getBoundingClientRect();
    if (r.top > window.innerHeight * 0.5 || r.bottom < 80)
      el.scrollIntoView?.({ behavior: reducedMotion() ? "auto" : "smooth", block: "start" });
  }, [pending]);

  const present = new Map<Who, { name: string; role: string }>();
  for (const m of messages.slice(0, shown)) if (!m.consent) present.set(m.who, { name: m.name, role: m.role });

  return (
    <section className="chat-stage frame" ref={stage} aria-label={t("agent.stage")}>
      <header className="roster">
        <ul>
          {[...present].map(([who, p]) => (
            <li key={who} className={next === who ? "typing" : ""}>
              <Avatar who={who} size={28} live={next === who} />
              <span>
                <b>{p.name}</b>
                <i>{next === who ? presence : p.role}</i>
              </span>
            </li>
          ))}
        </ul>
        <div className="roster-meta">
          {meta}
          {messages.length > 0 && (
            <span className="controls">
              <button
                className="quiet"
                onClick={() => {
                  follow.current = true;
                  setShown(0);
                }}
              >
                {t("chat.replay")}
              </button>
              {!caughtUp && (
                <button className="quiet" onClick={() => setShown(messages.length)}>
                  {t("chat.skip")}
                </button>
              )}
            </span>
          )}
        </div>
      </header>

      <div className="chat-scroll" ref={scroller} onScroll={onScroll} aria-live="polite">
        {messages.length === 0 && !pending && (
          <div className="stage-empty">
            <div className="stage-cast" aria-hidden>
              <Avatar who="agent" size={44} />
              <Avatar who="critic" size={44} />
              <Avatar who="sceptic" size={44} />
            </div>
            <p>{t("agent.empty.title")}</p>
            <p className="dim">{t("agent.empty.body")}</p>
          </div>
        )}
        <ol className="chat">
          {messages.slice(0, shown).map((m, i) => {
            const prev = messages[i - 1];
            const grouped = prev && prev.who === m.who && prev.name === m.name && !m.consent && !prev.consent;
            return (
              <li key={i} className={`msg msg-${m.who}${grouped ? " grouped" : ""}${m.consent ? " consent-msg" : ""}`}>
                {m.consent && <div className="consent">{t("trace.approved")}</div>}
                <div className="msg-avatar">{!grouped && <Avatar who={m.who} />}</div>
                <div className="msg-main">
                  {!grouped && (
                    <div className="msg-head">
                      <b>{m.name}</b>
                      <span className="role">{m.role}</span>
                      {m.via && <span className="role mono">{t("trace.via", { source: m.via })}</span>}
                      {m.ms !== undefined && <span className="ms num">{m.ms} ms</span>}
                    </div>
                  )}
                  {m.tool && (
                    <div className="msg-call">
                      <code>{m.tool}</code>
                      {m.to && <span>→ {m.to}</span>}
                    </div>
                  )}
                  {m.badge}
                  <div className="msg-body">{m.body}</div>
                </div>
              </li>
            );
          })}
          {next && (
            <li className={`msg typing-row msg-${next}`} key={`typing-${shown}`}>
              <div className="msg-avatar">
                <Avatar who={next} live />
              </div>
              <div className="msg-main">
                <div className="msg-head">
                  <b>{nextName}</b>
                  <span className="role">{presence}</span>
                </div>
                <span className="dots" aria-hidden>
                  <i />
                  <i />
                  <i />
                </span>
              </div>
            </li>
          )}
        </ol>
        {caughtUp && !pending && pinned && <div className="pinned">{pinned}</div>}
      </div>
      {behind && (
        <button className="to-latest" onClick={() => toLatest()}>
          {t("chat.latest")}
          <span aria-hidden>↓</span>
        </button>
      )}
    </section>
  );
}
