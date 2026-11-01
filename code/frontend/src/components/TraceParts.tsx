import type { GuardFinding, Step } from "../api";
import { useI18n } from "../i18n";
import type { Key } from "../i18n/en";
import { reasonText } from "../lib/reasons";
import { chf, metres, stay } from "../lib/format";
import { readSource, type Route } from "../lib/provenance";

// What the traveller's agent asked over MCP and what the other side answered, as message bodies for the group chat.
// Every line comes from a real tool call.

type Rec = Record<string, unknown>;
const list = (v: unknown) => (Array.isArray(v) ? (v as Rec[]) : []);

/** Business names as the agent learns them, so later turns can say "Hotel Rheinblick" instead of an id. */
export function namesFrom(steps: Step[]): Record<string, string> {
  const names: Record<string, string> = {};
  for (const s of steps) {
    for (const m of [...list(s.output.matches), ...list(s.output.excluded)]) names[String(m.id)] = String(m.name);
    if (s.output.id && s.output.name) names[String(s.output.id)] = String(s.output.name);
  }
  return names;
}

/**
 * Which hub a result came from. Never silent: a local result says "from this hub", so a row with no label never
 * reads as an origin nobody knows. Above one hop it adds the distance, the relays it travelled through, and the
 * whole route on demand. It changes no order: distance is already in the backend's score as `hop_decay`, and
 * sorting by it again here would quietly bury other hubs.
 */
export function Source({ match }: { match: Rec }) {
  const { t } = useI18n();
  const read = readSource({ hops: match.hops as number | undefined, provenance: match.provenance as Route | null });
  if (read.local) return <span className="ledger-source">{t("result.fromThisHub")}</span>;
  return (
    <span className="ledger-source away">
      {t("result.fromHub", { hub: read.origin })} · {t("result.hopsAway", { n: read.hops })}
      {read.relays.length > 0 && <> · {t("result.relayedVia", { hubs: read.relays.join(" · ") })}</>}
      {read.alsoReachedBy > 0 && <> · {t("result.alsoReachedBy", { n: read.alsoReachedBy })}</>}
      {read.path.length > 1 && (
        <details className="result-route">
          <summary>{t("result.route")}</summary>
          <span className="num">{read.path.join(" \u2192 ")}</span>
        </details>
      )}
    </span>
  );
}

export function Ask({ step, names }: { step: Step; names: Record<string, string> }) {
  const { t, intl } = useI18n();
  const i = step.input as Rec;
  const name = names[String(i.card_id)] ?? String(i.card_id ?? "");
  switch (step.tool) {
    case "hive_discover": {
      const wants = [
        ...(list(i.features) as unknown as string[]),
        i.near ? t("trace.near", { place: String(i.near) }) : "",
        i.max_price_chf ? t("trace.under", { price: chf(i.max_price_chf, intl) }) : "",
        i.check_in ? stay(i.check_in, i.check_out, intl) : "",
      ].filter(Boolean);
      return (
        <p>
          {t("trace.ask.discover", { kind: String(i.kind ?? "") })} <span className="wants">{wants.join(" · ")}</span>
        </p>
      );
    }
    case "hive_get_card":
      return <p>{t("trace.ask.card", { name })}</p>;
    case "hive_check_availability":
      return <p>{t("trace.ask.availability", { name, dates: stay(i.check_in, i.check_out, intl) })}</p>;
    case "hive_book":
      return (
        <p>
          {t("trace.ask.book", {
            name,
            guest: String(i.guest_name ?? ""),
            dates: stay(i.check_in, i.check_out, intl),
          })}
        </p>
      );
    case "hr_create_job":
      return <p>{t("hr.ask.create", { title: String(i.title ?? "") })}</p>;
    case "hr_find_people":
      return <p>{t("hr.ask.find", { skills: (list(i.skills) as unknown as string[]).join(", ") })}</p>;
    case "hub_connect":
      return <p>{t("hr.ask.connect")}</p>;
    case "hr_decide_intro":
      return <p>{t("hr.ask.decide")}</p>;
    case "hr_grant_cv":
      return <p>{t("hr.ask.grant")}</p>;
    case "hr_submit_cv":
      return <p>{t("hr.ask.submit")}</p>;
    default:
      return <p>{step.tool}</p>;
  }
}

function Discover({ o, guard }: { o: Rec; guard: GuardFinding[] }) {
  const { t, intl } = useI18n();
  const flagged = (m: Rec) => guard.some((f) => f.card_id === m.id && (f.source ?? m.source) === m.source);
  const matches = list(o.matches);
  const excluded = list(o.excluded);
  if (!matches.length && !excluded.length && list(o.errors).length) return <p>{t("trace.reply.discoverFailed")}</p>;
  return (
    <>
      <p>{t("trace.reply.discover", { fit: matches.length, total: matches.length + excluded.length })}</p>
      <ol className="ledger">
        {matches.map((m, n) => (
          <li key={`${m.source ?? ""}/${m.id}`} className={flagged(m) ? "flagged" : ""}>
            <span className="ledger-rank num">{n + 1}</span>
            <span className="ledger-name">
              {String(m.name)}
              <Source match={m} />
            </span>
            <span className="ledger-why">
              {flagged(m)
                ? t("trace.guard.row", { source: String(m.source) })
                : `${chf(m.from_price_chf, intl)} · ${metres(m.distance_m, intl)}`}
            </span>
            <span className="ledger-score num">{String(m.score)}</span>
          </li>
        ))}
        {excluded.map((x) => (
          <li key={`${x.source ?? ""}/${x.id}`} className="out">
            <span className="ledger-rank">–</span>
            <span className="ledger-name">
              {String(x.name)}
              <Source match={x} />
            </span>
            <span className="ledger-why">
              {(x.why_not as string[] | undefined)?.map((w) => reasonText(t, w)).join("; ")}
            </span>
            <span className="ledger-score num">{String(x.score)}</span>
          </li>
        ))}
      </ol>
    </>
  );
}

function SignedCard({ o, genuine }: { o: Rec; genuine: boolean | null }) {
  const { t } = useI18n();
  const trust = (o.trust ?? {}) as Rec;
  const att = list(trust.attestations);
  return (
    <>
      <p>
        {t(genuine === null ? "trace.reply.cardUnchecked" : genuine ? "trace.reply.card" : "trace.reply.cardForged", {
          version: String(o.version),
        })}
      </p>
      <dl className="seal">
        <dt>{t("trace.key")}</dt>
        <dd className="mono">{String(trust.public_key ?? "").slice(0, 16)}…</dd>
        {att.map((a) => (
          <div key={String(a.claim)} className="seal-row">
            <dt>{String(a.claim)}</dt>
            <dd>{t("trace.attestedBy", { who: String(a.attested_by) })}</dd>
          </div>
        ))}
      </dl>
    </>
  );
}

function Availability({ o, chosen }: { o: Rec; chosen?: string }) {
  const { t, intl } = useI18n();
  const units = list(o.available_units);
  if (!units.length) return <p>{t("trace.reply.full")}</p>;
  return (
    <ol className="ledger units">
      {units.map((u) => (
        <li key={String(u.id)} className={u.id === chosen ? "chosen" : ""}>
          <span className="ledger-name">{String(u.name)}</span>
          <span className="ledger-why num">
            {t("trace.perNight", { price: chf(u.price_chf, intl) })} · {t("trace.left", { n: String(u.left) })}
          </span>
          <span className="ledger-score num">{chf(u.total_chf, intl)}</span>
        </li>
      ))}
    </ol>
  );
}

/** What the agent's guard withheld from this answer, shown to the human word for word. */
export function Withheld({ findings }: { findings: GuardFinding[] }) {
  const { t } = useI18n();
  const codes = [...new Set(findings.flatMap((f) => f.codes))];
  return (
    <div className="withheld">
      <span className="status no">{t("trace.guard.title")}</span>
      {[...new Set(findings.map((f) => f.text))].map((text) => (
        <blockquote key={text}>{text}</blockquote>
      ))}
      <p>
        {codes.map((c) => t(`guard.${c}` as Key)).join(" · ")}. {t("trace.guard.note")}
      </p>
    </div>
  );
}

/** The agent's own signature check when it made one; otherwise what the Hive reported. */
export function genuine(step: Step): boolean | null {
  if (step.signature === "unchecked") return null;
  if (step.signature) return step.signature === "valid";
  if (step.tool !== "hive_get_card" || "error" in step.output) return null;
  return Boolean((step.output.trust as Rec | undefined)?.signature_valid);
}

export function Reply({ step, chosen }: { step: Step; chosen?: string }) {
  const { t } = useI18n();
  const o = step.output as Rec;
  if ("error" in o) return <p>{String(o.error)}</p>;
  switch (step.tool) {
    case "hive_discover":
      return <Discover o={o} guard={step.guard ?? []} />;
    case "hive_get_card":
      return <SignedCard o={o} genuine={genuine(step)} />;
    case "hive_check_availability":
      return <Availability o={o} chosen={chosen} />;
    case "hive_book":
      return <p>{t("trace.reply.book", { id: String(o.booking_id ?? "") })}</p>;
    case "hr_create_job":
      return <p>{t("hr.reply.create")}</p>;
    case "hr_find_people":
      return <p>{t("hr.reply.find")}</p>;
    case "hub_connect":
      return <p>{t("hr.reply.connect")}</p>;
    case "hr_decide_intro":
      return <p>{t("hr.reply.decide")}</p>;
    case "hr_grant_cv":
      return <p>{t("hr.reply.grant")}</p>;
    case "hr_submit_cv":
      return <p>{t("hr.reply.submit")}</p>;
    default:
      return <p>{t("trace.reply.done")}</p>;
  }
}
