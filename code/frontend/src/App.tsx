import { useEffect, useState } from "react";
import { api, type Health } from "./api";
import { LOCALES, LOCALE_NAMES, useI18n, type Locale } from "./i18n";
import TravellerAgent from "./pages/TravellerAgent";
import B6Bee from "./components/B6Bee";

// One page: the brand, whether the AI is live, the language. Everything else happens in the traveller's chat.
function Header() {
  const { t, locale, setLocale } = useI18n();
  const [health, setHealth] = useState<Health | null | undefined>(undefined);
  useEffect(() => {
    api
      .health()
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);
  const mode =
    health === undefined ? null : health === null ? (
      <span className="status no">{t("nav.down")}</span>
    ) : (
      <span
        className={`status ${health.llm !== "mock" ? "ok" : "warm"}`}
        title={`${health.model} / ${health.fast_model}`}
      >
        {health.llm !== "mock" ? t("nav.live") : t("nav.offline")}
      </span>
    );
  return (
    <nav className="nav">
      <div className="nav-inner">
        <span className="brand">
          <img src={`${import.meta.env.BASE_URL}brand/logo.svg`} alt="" width={30} height={30} />
          <span>Adobee Hive</span>
        </span>
        <div className="nav-end">
          {mode}
          <div className="locales" role="group" aria-label={t("nav.language")}>
            {LOCALES.map((l: Locale) => (
              <button
                key={l}
                className={l === locale ? "on" : ""}
                aria-pressed={l === locale}
                title={LOCALE_NAMES[l]}
                lang={l}
                onClick={() => setLocale(l)}
              >
                {l.toUpperCase()}
              </button>
            ))}
          </div>
        </div>
      </div>
    </nav>
  );
}

export default function App() {
  return (
    <>
      <Header />
      <main>
        <TravellerAgent />
      </main>
      <B6Bee />
    </>
  );
}
