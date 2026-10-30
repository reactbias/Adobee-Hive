import type { Step } from "../api";

// The agent-to-agent conversation: what the traveller's agent asked over MCP, and what the Hive answered.
// Every line comes from a real tool call; the raw JSON is one click away.

type Rec = Record<string, unknown>;
const list = (v: unknown) => (Array.isArray(v) ? (v as Rec[]) : []);

function ask(step: Step): string {
  const i = step.input as Rec;
  switch (step.tool) {
    case "hive_discover": {
      const parts = [
        String(i.kind ?? "anything"),
        ...(list(i.features) as unknown as string[]),
        i.near ? `near ${i.near}` : "",
        i.max_price_chf ? `max CHF ${i.max_price_chf}/night` : "",
        i.check_in ? `${i.check_in} to ${i.check_out}` : "",
        i.guests ? `${i.guests} guest${Number(i.guests) > 1 ? "s" : ""}` : "",
      ];
      return `Who can host this? ${parts.filter(Boolean).join(" · ")}`;
    }
    case "hive_get_card":
      return `Send me ${i.card_id}'s signed card.`;
    case "hive_check_availability":
      return `Is anything free at ${i.card_id}, ${i.check_in} to ${i.check_out}?`;
    case "hive_book":
      return `Book ${i.unit_id} at ${i.card_id} for ${i.guest_name}, ${i.check_in} to ${i.check_out}.`;
    default:
      return `${step.tool}(${Object.keys(i).join(", ")})`;
  }
}

function answer(step: Step, names: Record<string, string>): { who: string; text: string; ok: boolean } {
  const o = step.output as Rec;
  if ("error" in o) return { who: "Hive", text: String(o.error), ok: false };
  switch (step.tool) {
    case "hive_discover": {
      const m = list(o.matches);
      const x = list(o.excluded);
      const top = m[0] ? `Best fit ${m[0].name} (score ${m[0].score}). ` : "";
      return { who: "Hive", text: `${m.length} ${m.length === 1 ? "match" : "matches"}, ${x.length} ruled out, each with a reason. ${top}No paid placement.`, ok: m.length > 0 };
    }
    case "hive_get_card": {
      const t = (o.trust ?? {}) as Rec;
      const att = list(t.attestations).map((a) => `${a.claim} (${a.attested_by})`);
      return {
        who: String(o.name ?? "Business"),
        text: `Card v${o.version}, signed by the owner${att.length ? `. Attested: ${att.join(", ")}` : ""}.`,
        ok: Boolean(t.signature_valid),
      };
    }
    case "hive_check_availability": {
      const u = list(o.available_units);
      return {
        who: names[String((step.input as Rec).card_id)] ?? "Business",
        text: u.length ? u.map((x) => `${x.name}: CHF ${x.total_chf} total, ${x.left} left`).join(" · ") : "Fully booked.",
        ok: u.length > 0,
      };
    }
    case "hive_book":
      return { who: String(o.business ?? "Business"), text: `Confirmed ${o.booking_id}. Signed receipt issued.`, ok: o.status === "confirmed" };
    default:
      return { who: "Hive", text: "Done.", ok: true };
  }
}

export default function AgentTrace({ steps }: { steps: Step[] }) {
  const names: Record<string, string> = {};
  for (const s of steps) if (s.tool === "hive_get_card" && s.output.id) names[String(s.output.id)] = String(s.output.name);
  return (
    <ol className="a2a">
      {steps.map((s, n) => {
        const a = answer(s, names);
        return (
          <li key={n} style={{ animationDelay: `${n * 350}ms` }}>
            {s.tool === "hive_book" && <div className="a2a-human">You approved the booking</div>}
            <div className="a2a-msg mine">
              <span className="a2a-who">Your agent · <code>{s.tool}</code></span>
              {ask(s)}
            </div>
            <div className={`a2a-msg theirs ${a.ok ? "" : "bad"}`}>
              <span className="a2a-who">
                {a.who}
                {s.tool === "hive_get_card" && <span className={`chip ${a.ok ? "ok" : "no"}`}>{a.ok ? "signature valid" : "signature invalid"}</span>}
                {s.ms !== undefined && <span className="muted"> · {s.ms} ms</span>}
              </span>
              {a.text}
              <details>
                <summary className="muted">raw MCP exchange</summary>
                <pre>{JSON.stringify({ input: s.input, output: s.output }, null, 2)}</pre>
              </details>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
