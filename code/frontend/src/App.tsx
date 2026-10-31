import { useCallback, useEffect, useState } from "react";
import { api, chosenHub, chosenHubUrl, setChosenHub, type DirectoryHub, type Health } from "./api";
import { LOCALES, LOCALE_NAMES, useI18n, type Locale } from "./i18n";
import TravellerAgent from "./pages/TravellerAgent";
import AdminPanel from "./panels/AdminPanel";
import InstanceFinder from "./panels/InstanceFinder";
import Onboarding from "./panels/Onboarding";
import OwnerPanel from "./panels/OwnerPanel";
import NetworkPanel from "./panels/NetworkPanel";
import B6Bee from "./components/B6Bee";
import { SCREENS, type ScreenId } from "./components/Chapter";
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
/** Which screen the address asks for: the owner's, the live hub network, else the traveller's. */
const screenFromHash = (): ScreenId =>
  here().hash === "#business" ? "business" : here().hash === "#network" ? "network" : "travel";

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

// Two screens, one for each person the Hive serves. The header switches between them, says whether the AI is
// live, and switches the language.
function Header({
  screen,
  onLeaveAdmin,
  hub,
  onHealth,
}: {
  screen?: ScreenId;
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
          {SCREENS.map((c) => (
            <a key={c} className="link" href={`#${c}`} aria-current={screen === c ? "page" : undefined}>
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
  // The screen on show, from the hash. Both screens stay mounted, so a booking survives a look at the other.
  const [screen, setScreen] = useState<ScreenId>(screenFromHash);
  // The business the owner's screen opens on: the one just booked, when the traveller turns the page to it.
  const [business, setBusiness] = useState<string | undefined>(undefined);
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
      setScreen(screenFromHash());
      setHub((chosen) => chosen || hubFromUrl() || chosenHub());
    };
    window.addEventListener("popstate", sync);
    window.addEventListener("hashchange", sync);
    return () => {
      window.removeEventListener("popstate", sync);
      window.removeEventListener("hashchange", sync);
    };
  }, []);

  useEffect(() => {
    if (!admin) return;
    // A hash is one of the app's two screens and the panel has none of its own, so any hash while the panel is
    // open is in-app navigation: `#travel` means "show me the traveller's screen", and now it does.
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

  // The traveller turns the page to the business just booked: its owner sees the booking arrive.
  const openBusiness = (cardId: string) => {
    setBusiness(cardId);
    window.location.hash = "business";
    window.scrollTo?.({ top: 0 });
  };

  return (
    <>
      <Header screen={screen} hub={hub} onHealth={setReached} />
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
        <div hidden={screen !== "travel"}>
          <TravellerAgent key={`${hub}@${chosenHubUrl()}`} onOpenBusiness={openBusiness} />
        </div>
        <div hidden={screen !== "business"}>
          <OwnerPanel key={`${hub}@${chosenHubUrl()}/${business ?? ""}`} initial={business} />
        </div>
        {/* The hub network, live: its own screen, reached from the footer, so the two tabs stay for people. */}
        <div hidden={screen !== "network"}>
          <NetworkPanel key={`${hub}@${chosenHubUrl()}`} />
        </div>
      </main>
      <B6Bee>
        {/* Which Hive answered, always visible, and the one way to pick another. */}
        {hub && <span className="nav-hub-name">{t("nav.onHub", { hub })}</span>}
        <a className="btn quiet nav-hub" href="#network" aria-current={screen === "network" ? "page" : undefined}>
          {t("nav.network")}
        </a>
        <button className="quiet nav-hub" onClick={changeHub}>
          {t("finder.change")}
        </button>
      </B6Bee>
    </>
  );
}
