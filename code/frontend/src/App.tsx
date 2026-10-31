import { useCallback, useEffect, useState } from "react";
import { api, chosenHub, chosenHubUrl, setChosenHub, type DirectoryHub, type Health } from "./api";
import { LOCALES, LOCALE_NAMES, useI18n, type Locale } from "./i18n";
import TravellerAgent from "./pages/TravellerAgent";
import AdminPanel from "./panels/AdminPanel";
import InstanceFinder from "./panels/InstanceFinder";
import Onboarding from "./panels/Onboarding";
import B6Bee from "./components/B6Bee";
import { CHAPTERS } from "./components/Chapter";
import type { Key } from "./i18n/en";
import { hubIn, isHybrid, viewIn, without } from "./lib/view";

const here = () => new URL(typeof window === "undefined" ? "http://localhost/" : window.location.href);
/** `?admin` opens the hub's own panel instead of the app. Nothing on the public page links to it. */
const adminMode = () => viewIn(here().search) === "admin";
/**
 * `?hub=<id>` points the app at a Hive, as the pitch runbook does. `?hub` on its own means whatever this backend
 * serves. Without it the app runs on the Hive this build was deployed against, until a person picks another.
 */
const hubFromUrl = () => hubIn(here().search);

/** Rewrite the address without reloading. Used only to make it agree with what is on screen. */
const rewrite = (to: string) => history.replaceState(null, "", to);

/**
 * Forget the chosen hub and go back to the build's own. `?hub=` has to come out of the address too: left in, a
 * reload would re-apply it, which is exactly what it looked like when Change Hive seemed to do nothing.
 */
function forgetHub() {
  setChosenHub("");
  rewrite(without(here(), "hub"));
}

// One page in two chapters. The header names them, says whether the AI is live, and switches the language.
function Header({
  onLeaveAdmin,
  hub,
  onHealth,
}: {
  onLeaveAdmin?: () => void;
  hub?: string;
  onHealth?: (reached: boolean) => void;
}) {
  const { t, locale, setLocale } = useI18n();
  const [health, setHealth] = useState<Health | null | undefined>(undefined);
  useEffect(() => {
    let live = true;
    api
      .health()
      .then((h) => live && (setHealth(h), onHealth?.(true)))
      .catch(() => live && (setHealth(null), onHealth?.(false)));
    return () => {
      live = false;
    };
    // Re-asked whenever the app is pointed at a different Hive: the answer is about that hub, not about the page.
  }, [hub, onHealth]);
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
          <img src={`${import.meta.env.BASE_URL}brand/logo.svg`} alt="" width={28} height={28} />
          <span>Adobee Hive</span>
        </a>
        <nav className="nav-links" aria-label={t("nav.chapters")}>
          {CHAPTERS.map((c) => (
            <a key={c} className="link" href={`#${c}`}>
              {t(`chapter.${c}` as Key)}
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
  // Which Hive the app runs against: "" is the build's own. `?hub=` in the address or a pick in this tab sets it.
  const [hub, setHub] = useState(() => hubFromUrl() || chosenHub());
  // The finder is a view a person opens with Change Hive, never a gate on the way in.
  const [choosing, setChoosing] = useState(false);
  // Read from the address rather than frozen at mount, so the view and the URL cannot drift apart.
  const [admin, setAdmin] = useState(adminMode);
  // Whether the Hive the app is pointed at answered at all. Starts true: nothing is wrong until it is.
  const [reached, setReached] = useState(true);
  // The hive being applied to from the finder, if any. Not remembered: an application starts over on a reload.
  const [joining, setJoining] = useState<DirectoryHub | null>(null);
  const { t } = useI18n();

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

  if (choosing)
    return (
      <>
        <Header />
        <main>
          {joining ? (
            <Onboarding
              hub={joining}
              onBack={() => setJoining(null)}
              onUse={(picked) => {
                const row = joining;
                setChosenHub(picked, row && !row.home ? row.url || "" : "");
                setJoining(null);
                setHub(picked);
                setChoosing(false);
              }}
            />
          ) : (
            <InstanceFinder
              onPick={(picked) => {
                setHub(picked);
                setChoosing(false);
                setReached(true);
              }}
              onJoin={setJoining}
            />
          )}
        </main>
      </>
    );

  // Change Hive: drop the current pick, so the finder opens with nothing selected and the build's own backend.
  const changeHub = () => {
    forgetHub();
    setHub("");
    setReached(true);
    setChoosing(true);
  };

  return (
    <>
      <Header hub={hub} onHealth={setReached} />
      <main>
        {/* A chosen Hive that cannot be reached says so and offers the way back, rather than a dead page. */}
        {!reached && (
          <p className="error hub-unreachable" role="status">
            {t("app.hubUnreachable")}{" "}
            <button className="quiet" onClick={changeHub}>
              {t("finder.change")}
            </button>
          </p>
        )}
        {/* Keyed by the hub and its URL, so picking a different one starts the page over against that backend. */}
        <TravellerAgent key={`${hub}@${chosenHubUrl()}`} />
      </main>
      <B6Bee>
        {/* Which Hive answered, always visible, and the one way to pick another. */}
        {hub && <span className="nav-hub-name">{t("nav.onHub", { hub })}</span>}
        <button className="quiet nav-hub" onClick={changeHub}>
          {t("finder.change")}
        </button>
      </B6Bee>
    </>
  );
}
