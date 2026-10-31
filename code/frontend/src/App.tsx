import { useCallback, useEffect, useState } from "react";
import { api, chosenHub, setChosenHub, type Health } from "./api";
import { LOCALES, LOCALE_NAMES, useI18n, type Locale } from "./i18n";
import TravellerAgent from "./pages/TravellerAgent";
import AdminPanel from "./panels/AdminPanel";
import InstanceFinder from "./panels/InstanceFinder";
import B6Bee from "./components/B6Bee";
import { CHAPTERS } from "./components/Chapter";
import type { Key } from "./i18n/en";
import { hubIn, isHybrid, viewIn, without } from "./lib/view";

const here = () => new URL(typeof window === "undefined" ? "http://localhost/" : window.location.href);
/** `?admin` opens the hub's own panel instead of the app. Nothing on the public page links to it. */
const adminMode = () => viewIn(here().search) === "admin";
/**
 * `?hub=<id>` picks a Hive and skips the instance finder, so the pitch runbook can open straight into a booking
 * run. `?hub` on its own means the same thing for whatever this backend serves.
 */
const hubFromUrl = () => hubIn(here().search);

/** Rewrite the address without reloading. Used only to make it agree with what is on screen. */
const rewrite = (to: string) => history.replaceState(null, "", to);

/**
 * Forget the hub and go back to the finder with nothing selected. `?hub=` has to come out of the address too:
 * left in, a reload would re-apply it and bounce straight past the finder, which is exactly what it looked like
 * when Change Hive seemed to do nothing.
 */
function forgetHub() {
  setChosenHub("");
  rewrite(without(here(), "hub"));
}

// One page in three chapters. The header names them, says whether the AI is live, and switches the language.
function Header({ onChangeHub, onLeaveAdmin }: { onChangeHub?: () => void; onLeaveAdmin?: () => void }) {
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
            // The brand is a link home, so from the hub's own panel it leaves the panel like any other link.
            if (onLeaveAdmin) onLeaveAdmin();
            else rewrite(window.location.pathname + window.location.search);
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
  // Read from the address rather than frozen at mount, so the view and the URL cannot drift apart.
  const [admin, setAdmin] = useState(adminMode);

  /** Leave the hub's own panel and show the app, taking `?admin` out of the address with it. */
  const leaveAdmin = useCallback((keepHash: boolean) => {
    rewrite(without(here(), "admin", keepHash));
    setAdmin(false);
  }, []);

  useEffect(() => {
    // The address is the one source of truth for the view, so back and forward change what is on screen.
    const sync = () => {
      setAdmin(adminMode());
      setHub((chosen) => chosen || hubFromUrl() || chosenHub());
    };
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, []);

  useEffect(() => {
    if (!admin) return;
    // A hash is an anchor on the app's one page and the panel has none of its own, so any hash while the panel is
    // open is in-app navigation: `#travel` means "show me the traveller app", and now it does.
    const navigated = () => window.location.hash.length > 1 && leaveAdmin(true);
    window.addEventListener("hashchange", navigated);
    // A pasted `?admin#travel` claims two views at once. It resolves to the panel, with the stray anchor dropped,
    // rather than rendering a hybrid nobody asked for.
    if (isHybrid(window.location.search, window.location.hash))
      rewrite(window.location.pathname + window.location.search);
    return () => window.removeEventListener("hashchange", navigated);
  }, [admin, leaveAdmin]);

  if (admin)
    return (
      <>
        <Header onLeaveAdmin={() => leaveAdmin(false)} />
        <main>
          <AdminPanel onLeave={() => leaveAdmin(false)} />
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
