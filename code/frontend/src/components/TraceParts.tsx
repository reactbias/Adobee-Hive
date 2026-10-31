import type { Step } from "../api";
import { useI18n } from "../i18n";
import { chf, metres, stay } from "../lib/format";

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
    default:
      return <p>{step.tool}</p>;
  }
}

function Discover({ o }: { o: Rec }) {
  const { t, intl } = useI18n();
  const matches = list(o.matches);
  const excluded = list(o.excluded);
  return (
    <>
      <p>{t("trace.reply.discover", { fit: matches.length, total: matches.length + excluded.length })}</p>
      <ol className="ledger">
        {matches.map((m, n) => (
          <li key={String(m.id)}>
            <span className="ledger-rank num">{n + 1}</span>
            <span className="ledger-name">{String(m.name)}</span>
            <span className="ledger-why">
              {chf(m.from_price_chf, intl)} · {metres(m.distance_m, intl)}
            </span>
            <span className="ledger-score num">{String(m.score)}</span>
          </li>
        ))}
        {excluded.map((x) => (
          <li key={String(x.id)} className="out">
            <span className="ledger-rank">–</span>
            <span className="ledger-name">{String(x.name)}</span>
            <span className="ledger-why">{(x.why_not as string[] | undefined)?.join("; ")}</span>
            <span className="ledger-score num">{String(x.score)}</span>
          </li>
        ))}
      </ol>
    </>
  );
}

function SignedCard({ o }: { o: Rec }) {
  const { t } = useI18n();
  const trust = (o.trust ?? {}) as Rec;
  const att = list(trust.attestations);
  return (
    <>
      <p>{t("trace.reply.card", { version: String(o.version) })}</p>
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

export function Reply({ step, chosen }: { step: Step; chosen?: string }) {
  const { t } = useI18n();
  const o = step.output as Rec;
  if ("error" in o) return <p>{String(o.error)}</p>;
  switch (step.tool) {
    case "hive_discover":
      return <Discover o={o} />;
    case "hive_get_card":
      return <SignedCard o={o} />;
    case "hive_check_availability":
      return <Availability o={o} chosen={chosen} />;
    case "hive_book":
      return <p>{t("trace.reply.book", { id: String(o.booking_id ?? "") })}</p>;
    default:
      return <p>{t("trace.reply.done")}</p>;
  }
}
