import type { AskItem, AskReply } from "../api";
import { useI18n } from "../i18n";
import { reasonText } from "../lib/reasons";
import { day, money } from "../lib/format";

// A business's answer to a question, as a card inside the agent chat: its offers or events, straight from its own
// Hive card, with where an unclaimed card was compiled from.

export function AskCard({ reply }: { reply: AskReply }) {
  const { t, intl } = useI18n();
  const price = (i: AskItem) =>
    !i.price
      ? null
      : i.price.amount === 0
        ? t("ask.free")
        : t("ask.per", { price: money(i.price.amount, i.price.currency, intl), per: i.price.per });
  return (
    <div className="ask-card">
      <ol className="ask-items">
        {reply.items.map((i) => (
          <li key={i.id}>
            <h4>{i.title}</h4>
            {i.summary && <p className="dim">{i.summary}</p>}
            <p className="fine">
              {[i.date && day(i.date, intl), i.duration, price(i), ...i.why.map((w) => reasonText(t, w))]
                .filter(Boolean)
                .join(" · ")}
            </p>
          </li>
        ))}
      </ol>
      {reply.source && (
        <p className="fine dim">{t("ask.source", { url: reply.source.url, date: day(reply.source.read_on, intl) })}</p>
      )}
    </div>
  );
}
