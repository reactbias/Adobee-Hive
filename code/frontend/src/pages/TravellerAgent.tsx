import { useEffect, useRef, useState } from "react";
import {
  api,
  OFFLINE,
  shownError,
  type AgentOptions,
  type AgentResult,
  type AskResult,
  type Booking,
  type Card,
  type Refusal,
  type Step,
  type Unguarded,
} from "../api";
import Chapter from "../components/Chapter";
import Composer from "../components/Composer";
import GeneratedStage, { type Deal } from "../components/GeneratedStage";
import GroupChat, { type Segment } from "../components/GroupChat";
import NextSteps from "../components/NextSteps";
import { namesFrom } from "../components/TraceParts";
import ActivityPanel from "../panels/ActivityPanel";
import Introductions from "../panels/Introductions";
import NetworkPanel from "../panels/NetworkPanel";
import OwnerPanel from "../panels/OwnerPanel";
import { useI18n, useSample } from "../i18n";
import type { Key } from "../i18n/en";
import { chf, nights, stay } from "../lib/format";
import { pickNearby } from "../lib/next";
import { routeFor } from "../lib/route";
import { reasonText } from "../lib/reasons";
import JourneyLog, { useActivityLog } from "../components/JourneyLog";
import { sceneFor, type Scene } from "../lib/cardView";
import { hubScene } from "../lib/hubScene";
import Reach from "../components/Reach";
import { demoMode } from "../lib/demo";

const EXAMPLES: Key[] = ["agent.example.1", "agent.example.2", "agent.example.3"];
// The Try list: stays first, then any business; the same chat answers both.
const TRY: Key[] = ["agent.example.1", "card.try.person", "card.try.staff", "agent.example.2", "ask.ex1", "ask.ex2"];

type Rec = Record<string, unknown>;

function lastStep(steps: Step[], tool: string): Step | undefined {
  return [...steps].reverse().find((s) => s.tool === tool);
}

function lastOutput(steps: Step[], tool: string): Rec | undefined {
  return lastStep(steps, tool)?.output;
}

export default function TravellerAgent() {
  const { t, intl } = useI18n();
  const [input, setInput] = useSample(EXAMPLES);
  const [history, setHistory] = useState<{ role: string; content: string }[]>([]);
  const [result, setResult] = useState<AgentResult | null>(null);
  // A question about any business: the Hive's cards answer in the same chat.
  const [askResult, setAskResult] = useState<AskResult | null>(null);
  const [segments, setSegments] = useState<Segment[]>([]);
  // A Card covered the request: draw it. The agent chat opens only from Details.
  const [scene, setScene] = useState<Scene | null>(null);
  const [details, setDetails] = useState(false);
  const [guestName, setGuestName] = useState("");
  const [busy, setBusy] = useState(false);
  // The hubs are being asked; the agent is not involved yet.
  const [searching, setSearching] = useState(false);
  // How far the hubs are asked: this one only until the person chooses further.
  const [radius, setRadius] = useState(0);
  // Counts introductions asked for from a result, so the "How did it go?" panel reads them again.
  const [introduced, setIntroduced] = useState(0);
  const [error, setError] = useState("");
  const [rating, setRating] = useState(5);
  const [reviewText, setReviewText] = useSample(["agent.review.sample"]);
  const [reviewed, setReviewed] = useState("");
  const [booking, setBooking] = useState<Booking | null>(null);
  const [hotel, setHotel] = useState<Card | null>(null);
  const [nearby, setNearby] = useState<ReturnType<typeof pickNearby>>(null);
  // Demo only: plant a manipulated listing, and optionally run the agent without its rules.
  const [mirror, setMirror] = useState(false);
  const [rulesOff, setRulesOff] = useState(false);
  // The last chapter is the business's side of the same booking; Next steps can turn the page to it.
  const businessRef = useRef<HTMLElement>(null);
  const { events: log, pull: pullLog } = useActivityLog();
  // On a narrow screen Details opens under the cards: bring it into view once, without hiding them for good.
  const sideRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!details || !window.matchMedia?.("(max-width: 900px)").matches) return;
    sideRef.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });
  }, [details]);
  const box = useRef<HTMLTextAreaElement>(null);
  const openBusiness = () => businessRef.current?.scrollIntoView?.({ behavior: "smooth", block: "start" });

  // One tap on an example sends it: the page asks for clicks only where a person has to decide.
  async function send(raw = input, base = history, off = rulesOff, live = false) {
    const text = raw.trim();
    if (!text) return;
    // The log is read alongside the search, so Details opens on lines that are already here.
    void pullLog();
    // An answer to the agent's question ("From where to where?") completes the request it asked about.
    if (!live && !mirror && askResult?.clarify?.length) return askCards(text, `${askResult.question} ${text}`);
    // Naming one of the businesses just shown ("Pax please") picks it: its hand-off is held for a yes.
    const named =
      askResult && askResult.replies.length > 1 && !askResult.pending
        ? askResult.replies.find((x) => text.toLowerCase().includes(x.name.toLowerCase()))
        : undefined;
    if (!live && !mirror && named && askResult) return askCards(text, `${askResult.question} ${text}`, true);
    // The hubs answer first. The folders are only for when that call cannot be made.
    if (!live && !mirror) {
      setSearching(true);
      setError("");
      const drawn = await hubScene(text, radius)
        .catch(() => null)
        .then((found) => found ?? sceneFor(text))
        .finally(() => setSearching(false));
      if (drawn) {
        setScene(drawn);
        setDetails(false);
        setError("");
        setInput("");
        setHistory([...base, { role: "user", content: text }]);
        return;
      }
    }
    if (!live) setScene(null);
    if (!mirror && routeFor(text, Boolean(result)) === "ask") return askCards(text);
    setAskResult(null);
    const messages = [...base, { role: "user", content: text }];
    const options: AgentOptions = mirror ? { scenario: "injection", rules: off ? "off" : "on" } : {};
    setBusy(true);
    setError("");
    setReviewed("");
    setBooking(null);
    setHistory(messages);
    setInput("");
    const before = base.length ? segments : [];
    setSegments([...before, { kind: "guest", text }]);
    try {
      const out = await api.agent(messages, options);
      setResult(out);
      setHistory([...messages, { role: "assistant", content: out.reply }]);
      const guest = String(out.pending?.input.guest_name ?? "").split(" ")[0];
      if (guest) setGuestName(guest);
      setSegments([
        ...before,
        { kind: "guest", text },
        ...(before.length ? [] : [{ kind: "ack" } as Segment]),
        { kind: "steps", steps: out.steps },
        ...(out.critic ? [{ kind: "critic", critic: out.critic } as Segment] : []),
        ...(out.second_opinion ? [{ kind: "opinion", opinion: out.second_opinion } as Segment] : []),
        ...(out.consensus !== undefined ? [{ kind: "consensus", agreed: out.consensus } as Segment] : []),
        { kind: "agent", text: out.reply },
        ...(out.guard?.length ? [{ kind: "refused" } as Segment] : []),
      ]);
    } catch (e) {
      setError(shownError((e as Error).message));
      // Details is optional. A dead backend leaves the card on screen, without the raw status
      // and without putting the request back into the search bar.
      if (live) {
        setDetails(false);
        return;
      }
      setHistory(base);
      setSegments(segments);
      setInput(messages[messages.length - 1].content);
    } finally {
      setBusy(false);
    }
  }

  // Any business: one call to the Hive's cards. Nothing is done until the person says yes to a hand-off.
  async function askCards(text: string, query = text, pick = false) {
    const before = history.length ? segments : [];
    setBusy(true);
    setError("");
    setInput("");
    setResult(null);
    setBooking(null);
    setHistory([...history, { role: "user", content: text }]);
    setSegments([...before, { kind: "guest", text }]);
    try {
      const r = pick ? await api.ask(query, null, true) : await api.ask(query, null);
      setAskResult(r);
      setHistory((h) => [
        ...h,
        { role: "assistant", content: r.answer ?? t("chat.ask.found", { n: r.replies.length }) },
      ]);
      const asked: Segment[] = [
        ...before,
        { kind: "guest", text },
        ...(before.length ? [] : [{ kind: "ack" } as Segment]),
        { kind: "ask", result: r },
      ];
      setSegments(asked);
      // No card answers: the agents look beyond the Hive, on the public web, in the same conversation.
      if (!r.replies.length && !r.clarify?.length) {
        const scouted = await api.scout(query).catch(() => null);
        if (scouted?.result) setAskResult(scouted.result);
        setSegments([...asked, { kind: "scout", scout: scouted }]);
      }
    } catch (e) {
      setError(shownError((e as Error).message));
      setHistory(history);
      setSegments(segments);
      setInput(text);
    } finally {
      setBusy(false);
    }
  }

  async function approveAsk() {
    const held = askResult?.pending;
    if (!askResult || !held) return;
    setBusy(true);
    setError("");
    try {
      const handoff = await api.askApprove(held.id);
      setAskResult({ ...askResult, pending: null });
      setSegments((seg) => [...seg, { kind: "consent", handoff: true }, { kind: "handoff", handoff }]);
    } catch (e) {
      setError(shownError((e as Error).message));
    } finally {
      setBusy(false);
    }
  }

  function declineAsk() {
    if (!askResult) return;
    setAskResult({ ...askResult, pending: null });
    setSegments((seg) => [...seg, { kind: "agent", text: t("agent.declined") }]);
  }

  // The only step a human takes: say yes. The agent then sends the booking it held back.
  async function approve() {
    if (!result?.pending) return;
    const cardId = String(result.pending.input.card_id ?? "");
    const wanted = (result.steps.find((s) => s.tool === "hive_discover")?.input.features ?? []) as string[];
    setBusy(true);
    setError("");
    try {
      const done = await api.approve(result.pending);
      setResult({ ...result, steps: [...result.steps, ...done.steps], pending: null });
      setBooking(done.booking);
      // Context for the next steps, from the Hive itself. If it is out of reach the tiles simply shrink.
      const [card, cafes] = await Promise.all([
        api.card(cardId).catch(() => null),
        api.cards("cafe").catch(() => [] as Card[]),
      ]);
      setHotel(card);
      setNearby(pickNearby(cafes, wanted));
      setHistory((h) => [...h, { role: "assistant", content: done.reply }]);
      setSegments((seg) => [
        ...seg,
        { kind: "consent" },
        { kind: "steps", steps: done.steps },
        ...(done.booking ? [{ kind: "receipt", booking: done.booking } as Segment] : []),
        { kind: "agent", text: done.reply },
        ...(done.booking ? [{ kind: "next" } as Segment] : []),
      ]);
    } catch (e) {
      setError(shownError((e as Error).message));
    } finally {
      setBusy(false);
    }
  }

  function decline() {
    if (!result) return;
    setResult({ ...result, pending: null });
    setHistory((h) => [...h, { role: "assistant", content: t("agent.declined") }]);
    setSegments((seg) => [...seg, { kind: "agent", text: t("agent.declined") }]);
  }

  // From the rules-off result: the same request, now with the agent's rules on.
  function rerunGuarded() {
    const lastAsk = [...history].reverse().find((m) => m.role === "user");
    if (!lastAsk) return;
    setRulesOff(false);
    send(lastAsk.content, [], false);
  }

  // The drawn request has been handed to the agent: its run is what both the cards and Details show.
  const asked = Boolean(scene && segments.some((s) => s.kind === "guest" && s.text === scene.query));

  /** Hand the drawn request to the agent once; the cards' yes and Details share that one run. */
  function askAgent() {
    if (!scene || busy || asked) return;
    void send(scene.query, history.slice(0, -1), rulesOff, true);
  }

  function openDetails() {
    if (!scene) return;
    if (details) {
      setDetails(false);
      return;
    }
    if (busy) return;
    setDetails(true);
    // The log and the chat start together. Neither waits for the other.
    void pullLog();
    askAgent();
  }

  function reset() {
    setHistory([]);
    setScene(null);
    setDetails(false);
    setResult(null);
    setAskResult(null);
    setSegments([]);
    setGuestName("");
    setBooking(null);
    setHotel(null);
    setNearby(null);
    setReviewed("");
    setError("");
    setRadius(0);
  }

  async function leaveReview() {
    if (!booking) return;
    try {
      const r = await api.review(booking.receipt, rating, reviewText);
      setReviewed(t("agent.review.stored", { id: r.review_id }));
    } catch (e) {
      setReviewed((e as Error).message);
    }
  }

  const steps = result?.steps ?? [];
  const names = namesFrom(steps);
  const pending = result?.pending?.input as Rec | undefined;
  const counterpartId = String(pending?.card_id ?? lastOutput(steps, "hive_get_card")?.id ?? "");
  const counterpart = names[counterpartId] ?? t("trace.hive");

  // What the gate needs to say, taken from what the business itself answered.
  const unit = list(lastOutput(steps, "hive_check_availability")?.available_units).find(
    (u) => u.id === pending?.unit_id,
  );
  const policies = (lastOutput(steps, "hive_check_availability")?.policies ?? {}) as Record<string, string>;
  const why = (list(lastOutput(steps, "hive_discover")?.matches).find((m) => m.id === pending?.card_id)?.why ??
    []) as string[];

  // The business chapter opens on the hotel just booked, so its owner sees the booking arrive.
  const owner = hotel?.id ? hotel : null;

  // One gate and one receipt, drawn under the card and in Details alike: approving in either is the same yes.
  const gate = pending && (
    <div className="gate">
      <span className="eyebrow">{t("agent.gate.eyebrow")}</span>
      {result?.consensus !== undefined && (
        <p className={`status ${result.consensus ? "ok" : "no"}`}>
          {t(result.consensus ? "chat.consensus.agree" : "chat.consensus.split")}
        </p>
      )}
      <h3>
        {t("agent.gate.question", {
          unit: String(unit?.name ?? pending.unit_id),
          name: counterpart,
        })}
      </h3>
      <dl className="facts">
        <div>
          <dt>{t("agent.fact.dates")}</dt>
          <dd>{stay(pending.check_in, pending.check_out, intl)}</dd>
        </div>
        <div>
          <dt>{t("agent.fact.nights")}</dt>
          <dd>{nights(pending.check_in, pending.check_out)}</dd>
        </div>
        <div>
          <dt>{t("agent.fact.guest")}</dt>
          <dd>{String(pending.guest_name)}</dd>
        </div>
        {unit && (
          <div>
            <dt>{t("agent.fact.total")}</dt>
            <dd>{chf(unit.total_chf, intl)}</dd>
          </div>
        )}
      </dl>
      {result?.second_opinion && (
        <div className={`opinion ${result.second_opinion.verdict}`}>
          <span className="label">
            {t("agent.opinion.from", { by: result.second_opinion.by })}
            {result.second_opinion.fallback ? ` (${result.second_opinion.fallback})` : ""}
          </span>
          <p>
            <span className={`status ${result.second_opinion.verdict === "agree" ? "ok" : "no"}`}>
              {t(result.second_opinion.verdict === "agree" ? "agent.opinion.agree" : "agent.opinion.concern")}
            </span>{" "}
            {result.second_opinion.note}
          </p>
        </div>
      )}
      {result?.critic?.verdict === "concern" && (
        <div className="opinion concern">
          <span className="label">{t("chat.name.critic")}</span>
          <p>{result.critic.note}</p>
        </div>
      )}
      {why.length > 0 && (
        <div className="why">
          <span className="label">{t("agent.gate.why")}</span>
          <p>{why.map((w) => reasonText(t, w)).join(" · ")}</p>
        </div>
      )}
      <div className="row gate-actions">
        <button onClick={approve}>{t("agent.approve")}</button>
        <button className="quiet" onClick={decline}>
          {t("agent.decline")}
        </button>
      </div>
      <p className="fine">
        {t("agent.gate.fine")}
        {policies.cancellation ? ` ${policies.cancellation}.` : ""}
      </p>
    </div>
  );
  const receipt = booking && (
    <article className="receipt">
      <header className="spread">
        <span className="status ok">{t("agent.receipt.eyebrow")}</span>
        <span className="mono dim">{booking.booking_id}</span>
      </header>
      <h3>{booking.business}</h3>
      <dl className="facts">
        <div>
          <dt>{t("agent.fact.room")}</dt>
          <dd>{booking.unit_name}</dd>
        </div>
        <div>
          <dt>{t("agent.fact.dates")}</dt>
          <dd>{stay(booking.check_in, booking.check_out, intl)}</dd>
        </div>
        <div>
          <dt>{t("agent.fact.total")}</dt>
          <dd>{chf(booking.total_chf, intl)}</dd>
        </div>
      </dl>
      <p className="dim small">
        {booking.payment}. {booking.cancellation}
      </p>
      <div className="signature">
        <span className="label">{t("agent.receipt.signature")}</span>
        <code>{booking.receipt}</code>
      </div>
      <div className="review">
        <span className="label">{t("agent.review.title")}</span>
        <div className="stars" role="radiogroup" aria-label={t("agent.review.rating")}>
          {[1, 2, 3, 4, 5].map((n) => (
            <button
              key={n}
              role="radio"
              aria-checked={rating === n}
              aria-label={String(n)}
              className={n <= rating ? "on" : ""}
              onClick={() => setRating(n)}
            >
              ★
            </button>
          ))}
        </div>
        <div className="row">
          <input value={reviewText} onChange={(e) => setReviewText(e.target.value)} className="field" />
          <button className="ghost" onClick={leaveReview} disabled={!reviewText.trim()}>
            {t("agent.review.send")}
          </button>
        </div>
        {reviewed && <p className="dim small">{reviewed}</p>}
      </div>
    </article>
  );
  const followUp = booking && (
    <NextSteps booking={booking} hotel={hotel} nearby={nearby} onOpenBusiness={openBusiness} />
  );
  const lastSaid = [...segments].reverse().find((s) => s.kind === "agent");
  const deal: Deal = asked
    ? {
        heldFor: pending ? String(pending.card_id) : undefined,
        heldName: counterpart,
        gate,
        bookedFor: booking ? String(lastStep(steps, "hive_book")?.input.card_id ?? "") : undefined,
        receipt: (
          <>
            {receipt}
            {followUp}
          </>
        ),
        answer: !busy && !pending && !booking && lastSaid?.kind === "agent" ? lastSaid.text : undefined,
        working: busy,
        onAsk: askAgent,
      }
    : { working: false, onAsk: askAgent };

  return (
    <>
      <Chapter
        id="travel"
        stack
        headingLevel={1}
        eyebrow={t("agent.eyebrow")}
        heading="agent.title"
        lead={t("agent.lead")}
        side={
          <div className="search-top">
            <Composer
              bar
              id="intent"
              label={history.length ? t("agent.followUp") : t("agent.intent")}
              value={input}
              onChange={setInput}
              onSend={(text) => send(text)}
              busy={busy || searching}
              sendLabel={t("agent.send")}
              busyLabel={searching ? t("card.searching") : t("agent.sending")}
              placeholder={t("agent.placeholder")}
              tryLabel={t("agent.try")}
              examples={history.length || searching ? [] : TRY.map((k) => t(k))}
              boxRef={box}
              secondary={
                history.length > 0 && (
                  <button
                    className="quiet"
                    onClick={() => {
                      reset();
                      box.current?.focus();
                    }}
                    disabled={busy}
                  >
                    {t("agent.newTrip")}
                  </button>
                )
              }
            />
            <Reach radius={radius} disabled={busy || searching} onChange={setRadius} />
            {/* The manipulation demo stays one tap away, folded so the brief fits the screen. */}
            {demoMode() && (
              <details className="stress">
                <summary className="eyebrow">{t("agent.test.eyebrow")}</summary>
                <fieldset>
                  <label className="check">
                    <input
                      type="checkbox"
                      checked={mirror}
                      disabled={busy}
                      onChange={(e) => {
                        setMirror(e.target.checked);
                        if (!e.target.checked) setRulesOff(false);
                      }}
                    />
                    <span>{t("agent.test.injection")}</span>
                  </label>
                  <label className={`check danger${mirror ? "" : " off"}`}>
                    <input
                      type="checkbox"
                      checked={rulesOff}
                      disabled={busy || !mirror}
                      onChange={(e) => setRulesOff(e.target.checked)}
                    />
                    <span>{t("agent.test.rulesOff")}</span>
                  </label>
                </fieldset>
                <a className="link" href="#activity">
                  {t("activity.link")}
                </a>
              </details>
            )}
            {error && <p className="error">{error === OFFLINE ? t("error.offline") : error}</p>}
          </div>
        }
      >
        {searching && !scene && (
          <div className="result-pending" role="status">
            <span className="pulse" aria-hidden />
            {t("card.searching")}
          </div>
        )}
        <div className={scene && details ? "journey split" : "journey"}>
          {scene && (
            <GeneratedStage
              key={scene.query}
              scene={scene}
              onDetails={openDetails}
              detailsOpen={details}
              deal={deal}
              onConnected={() => setIntroduced((n) => n + 1)}
            />
          )}
          {(details || (!scene && history.length > 0)) && (
            <div className="journey-side" ref={sideRef}>
              <GroupChat
                full={Boolean(scene && details)}
                segments={segments}
                guestName={guestName || t("chat.you")}
                pending={busy}
                meta={
                  <>
                    {scene && (
                      <button className="quiet" onClick={() => setDetails(false)}>
                        {t("card.back")}
                      </button>
                    )}
                    <span className="stage-meta">
                      {result ? (
                        <span>
                          {result.mode === "claude"
                            ? t("agent.mode.claude")
                            : result.mode === "openai"
                              ? t("agent.mode.openai")
                              : t("agent.mode.offline") + (result.fallback ? ` (${result.fallback})` : "")}
                        </span>
                      ) : (
                        <span>{t("agent.mode.ready")}</span>
                      )}
                      <span>{t("agent.meta.mcp")}</span>
                      {result?.scenario ? (
                        <span>{t("agent.meta.mirror")}</span>
                      ) : (
                        <span>{t("agent.meta.noWebsite")}</span>
                      )}
                      {result?.rules === "off" && <span className="danger">{t("agent.meta.rulesOff")}</span>}
                    </span>
                  </>
                }
                refused={result?.guard?.length ? <Refused refusals={result.guard} /> : undefined}
                pinned={
                  askResult?.pending ? (
                    <div className="gate">
                      <span className="eyebrow">{t("agent.gate.eyebrow")}</span>
                      <h3>{t("ask.pending.title")}</h3>
                      <p>
                        {t("ask.pending.body", { business: askResult.pending.business, item: askResult.pending.item })}
                      </p>
                      <div className="row gate-actions">
                        <button onClick={approveAsk} disabled={busy}>
                          {t("ask.pending.approve")}
                        </button>
                        <button className="quiet" onClick={declineAsk}>
                          {t("ask.pending.decline")}
                        </button>
                      </div>
                    </div>
                  ) : result?.unguarded ? (
                    <RulesOff damage={result.unguarded} steps={steps} onRerun={rerunGuarded} />
                  ) : (
                    gate
                  )
                }
                followUp={followUp}
                receipt={receipt}
              />
              {scene && details && <JourneyLog events={log} />}
            </div>
          )}
        </div>
      </Chapter>
      <Introductions refresh={introduced} />
      <OwnerPanel
        key={`${owner?.id ?? ""}/${booking?.booking_id ?? ""}`}
        initial={owner?.id}
        sectionRef={businessRef}
      />
      <NetworkPanel />
      {demoMode() && <ActivityPanel />}
    </>
  );
}

const list = (v: unknown) => (Array.isArray(v) ? (v as Rec[]) : []);

/** The listings the agent refused this run, and why: kept on the stage so the human sees the attempt. */
function Refused({ refusals }: { refusals: Refusal[] }) {
  const { t } = useI18n();
  return (
    <aside className="refused">
      <span className="eyebrow">{t("agent.refused.eyebrow")}</span>
      {refusals.map((r) => (
        <div key={`${r.source}/${r.card_id}`}>
          <h4>{t("agent.refused.from", { name: r.business ?? String(r.card_id), source: r.source })}</h4>
          <ul>
            {r.codes.map((c) => (
              <li key={c}>{t(`guard.${c}` as Key)}</li>
            ))}
          </ul>
        </div>
      ))}
      <p className="fine">{t("agent.refused.fine")}</p>
    </aside>
  );
}

/** Demo only: what an agent without rules would have done. Clearly labelled; nothing here was sent. */
function RulesOff(props: { damage: Unguarded; steps: Step[]; onRerun: () => void }) {
  const { t, intl } = useI18n();
  const input = props.damage.would_call.input as Rec;
  const card = lastOutput(props.steps, "hive_get_card");
  const unit = list(card?.units).find((u) => u.id === input.unit_id);
  return (
    <div className="gate unguarded">
      <span className="eyebrow">{t("agent.unguarded.eyebrow")}</span>
      <h3>
        {t("agent.unguarded.title", {
          unit: String(unit?.name ?? input.unit_id),
          name: String(card?.name ?? input.card_id),
        })}
      </h3>
      <dl className="facts">
        <div>
          <dt>{t("agent.fact.dates")}</dt>
          <dd>{stay(input.check_in, input.check_out, intl)}</dd>
        </div>
        <div>
          <dt>{t("agent.fact.total")}</dt>
          <dd>{chf(props.damage.total_chf, intl)}</dd>
        </div>
      </dl>
      <div>
        <span className="label">{t("agent.unguarded.broken")}</span>
        <ul className="broken">
          {props.damage.broken.map((b) => (
            <li key={b.code}>
              {t(`broken.${b.code}` as Key, {
                price: chf(b.price_chf, intl),
                budget: chf(b.budget_chf, intl),
              })}
            </li>
          ))}
        </ul>
      </div>
      <div className="row gate-actions">
        <button onClick={props.onRerun}>{t("agent.unguarded.rerun")}</button>
      </div>
      <p className="fine">{t("agent.unguarded.fine")}</p>
    </div>
  );
}
