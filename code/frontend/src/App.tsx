import { useEffect, useState } from "react";
import { api, chosenHub, setChosenHub, type Health } from "./api";
import { LOCALES, LOCALE_NAMES, useI18n, type Locale } from "./i18n";
import TravellerAgent from "./pages/TravellerAgent";
import AdminPanel from "./panels/AdminPanel";
import InstanceFinder from "./panels/InstanceFinder";
import B6Bee from "./components/B6Bee";
import { CHAPTERS } from "./components/Chapter";
import type { Key } from "./i18n/en";

const search = () => new URLSearchParams(typeof window === "undefined" ? "" : window.location.search);
/** `?admin` opens the hub's own panel instead of the app. Nothing on the public page links to it. */
const adminMode = () => search().has("admin");
/**
 * `?hub=<id>` picks a Hive and skips the instance finder, so the pitch runbook can open straight into a booking
 * run. `?hub` on its own means the same thing for whatever this backend serves.
 */
const hubFromUrl = () => (search().has("hub") ? search().get("hub") || "local" : "");

/**
 * Forget the hub and go back to the finder with nothing selected. `?hub=` has to come out of the address too:
 * left in, a reload would re-apply it and bounce straight past the finder, which is exactly what it looked like
 * when Change Hive seemed to do nothing.
 */
function forgetHub() {
  setChosenHub("");
  const params = search();
  params.delete("hub");
  const query = params.toString();
  history.replaceState(null, "", `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`);
}

// One page in three chapters. The header names them, says whether the AI is live, and switches the language.
function Header({ onChangeHub }: { onChangeHub?: () => void }) {
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
          {onChangeHub && (
            <button className="quiet nav-hub" onClick={onChangeHub}>
              {t("finder.change")}
            </button>
          )}
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
  // Which Hive the app runs against. The finder sets it; `?hub=` in the address skips the finder entirely.
  const [hub, setHub] = useState(() => hubFromUrl() || chosenHub());
  const [admin] = useState(adminMode);

  if (admin)
    return (
      <>
        <Header />
        <main>
          <AdminPanel onLeave={() => (window.location.search = "")} />
        </main>
      </>
    );

  if (!hub)
    return (
      <>
        <Header />
        <main>
          <InstanceFinder onPick={setHub} />
        </main>
      </>
    );

  return (
    <>
      <Header
        onChangeHub={() => {
          forgetHub();
          setHub("");
        }}
      />
      <main>
        {/* Keyed by the hub, so picking a different one starts the page over instead of layering on the last. */}
        <TravellerAgent key={hub} />
      </main>
      <B6Bee />
    </>
  );
}
