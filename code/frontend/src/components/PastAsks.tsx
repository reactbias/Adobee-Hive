import { useI18n } from "../i18n";
import { forgetAsks } from "../lib/asks";

/**
 * What you asked before: each one a button that asks it again, plus one that forgets the lot.
 *
 * It says where the list lives, because a person reading their own search history on a federated directory is
 * entitled to know whether the hub has it too. It does not: see `lib/asks.ts`.
 *
 * Nothing is drawn before the first ask, so a visitor's first screen is not cluttered by an empty heading.
 */
export default function PastAsks({
  asks,
  busy = false,
  onAsk,
  onForget,
}: {
  asks: string[];
  busy?: boolean;
  onAsk: (ask: string) => void;
  onForget: () => void;
}) {
  const { t } = useI18n();
  if (!asks.length) return null;
  return (
    <section className="past-asks" aria-labelledby="past-asks-title">
      <div className="spread">
        <span className="eyebrow" id="past-asks-title">
          {t("asks.title")}
        </span>
        <button
          className="quiet small"
          onClick={() => {
            forgetAsks();
            onForget();
          }}
        >
          {t("asks.forget")}
        </button>
      </div>
      <ul className="chips">
        {asks.map((ask) => (
          <li key={ask}>
            {/* The label says what the button does; the chip is clipped when the request was a long one, so
                the full text lives in the accessible name and in the tooltip rather than in the layout. */}
            <button
              className="chip"
              disabled={busy}
              onClick={() => onAsk(ask)}
              aria-label={t("asks.again", { ask })}
              title={ask}
            >
              {ask}
            </button>
          </li>
        ))}
      </ul>
      <p className="fine">{t("asks.only")}</p>
    </section>
  );
}
