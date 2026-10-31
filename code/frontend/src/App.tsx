import { useEffect, useState } from "react";
import { api, type Health } from "./api";
import { LOCALES, LOCALE_NAMES, useI18n, type Locale } from "./i18n";
import TravellerAgent from "./pages/TravellerAgent";
import B6Bee from "./components/B6Bee";
import { CHAPTERS } from "./components/Chapter";
import type { Key } from "./i18n/en";

// One page in three chapters. The header names them, says whether the AI is live, and switches the language.
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
    <header className="nav">
      <div className="nav-inner">
        <a
          className="brand"
          href="#top"
          aria-label="Adobee Hive"
          onClick={(e) => {
            e.preventDefault();
            const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
            window.scrollTo({ top: 0, behavior: still ? "auto" : "smooth" });
            history.replaceState(null, "", window.location.pathname + window.location.search);
          }}
        >
          <img src={`${import.meta.env.BASE_URL}brand/logo.svg`} alt="" width={30} height={30} />
          <span>Adobee Hive</span>
        </a>
        <nav className="nav-links" aria-label={t("nav.chapters")}>
          {CHAPTERS.map((c, i) => (
            <a key={c} className="link" href={`#${c}`}>
              <span className="num">{i + 1}</span> {t(`chapter.${c}` as Key)}
            </a>
          ))}
        </nav>
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
    </header>
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
