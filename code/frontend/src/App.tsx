import { useCallback, useEffect, useState } from "react";
import { api, chosenHub, chosenHubUrl, setChosenHub, type DirectoryHub } from "./api";
import { LOCALES, LOCALE_NAMES, useI18n, type Locale } from "./i18n";
import TravellerAgent from "./pages/TravellerAgent";
import AdminPanel from "./panels/AdminPanel";
import InstanceFinder from "./panels/InstanceFinder";
import Onboarding from "./panels/Onboarding";
import OwnerPanel from "./panels/OwnerPanel";
import NetworkPanel from "./panels/NetworkPanel";
import B6Bee from "./components/B6Bee";
import BackendStatus from "./components/BackendStatus";
import ThemeToggle from "./components/ThemeToggle";
import {
  canonicalHash,
  joinHash,
  joinHubIn,
  namesScreen,
  screenFor,
  SCREENS,
  type ScreenId,
} from "./components/Chapter";
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
/** Which screen the address asks for: offering, the live hub network, else finding. Old names still read. */
const screenFromHash = (): ScreenId => screenFor(here().hash);

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

// The find, offer and network screens share the language switch and backend troubleshooting.
function Header({
  screen,
  onLeaveAdmin,
  hub,
  onHealth,
}: {
  screen?: ScreenId;
  onLeaveAdmin?: () => void;
  hub?: string;
  onHealth?: (reached: boolean | undefined) => void;
}) {
  const { t, locale, setLocale } = useI18n();
  return (
    <>
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
            {/* The mark is one clay line. BRAND.md keeps a lit-clay copy for dark grounds, and the swap
                belongs here rather than in CSS: the stylesheet is not allowed to name the logo's colours. */}
            <picture>
              <source srcSet={`${import.meta.env.BASE_URL}brand/logo-light.svg`} media="(prefers-color-scheme: dark)" />
              <img src={`${import.meta.env.BASE_URL}brand/logo.svg`} alt="" width={28} height={28} />
            </picture>
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
            <ThemeToggle />
          </div>
        </div>
      </header>
      <BackendStatus hub={hub} onHealth={onHealth} />
    </>
  );
}

export default function App() {
  // Which Hive the app runs against: "" is the build's own. `?hub=` in the address or a pick in this tab sets it.
  const [hub, setHub] = useState(() => hubFromUrl() || chosenHub());
  // The finder is a view a person opens with Change Hive, never a gate on the way in. A join hash lands here
  // too: the Hive list is what sits behind an application.
  const [choosing, setChoosing] = useState(() => Boolean(joinHubIn(here().hash)));
  // Read from the address rather than frozen at mount, so the view and the URL cannot drift apart.
  const [admin, setAdmin] = useState(adminMode);
  // The screen on show, from the hash. Both screens stay mounted, so a booking survives a look at the other.
  const [screen, setScreen] = useState<ScreenId>(screenFromHash);
  // The business the owner's screen opens on: the one just booked, when the traveller turns the page to it.
  const [business, setBusiness] = useState<string | undefined>(undefined);
  // Unknown until the selected backend answers; planner mode is tracked separately in the status display.
  const [reached, setReached] = useState<boolean | undefined>(undefined);
  // Which hive is being applied to: read from the address, so back, forward, a reload and a header link all
  // move this view like any other. `joining` is only the directory row for that id, fetched when a reload
  // arrives on the hash without one.
  const [joinHub, setJoinHub] = useState(() => joinHubIn(here().hash));
  const [joining, setJoining] = useState<DirectoryHub | null>(null);
  const { t } = useI18n();

  /** Leave the hub's own panel and show the app, taking `?admin` out of the address with it. */
  const leaveAdmin = useCallback((keepHash: boolean) => {
    rewrite(without(here(), "admin", keepHash));
    setAdmin(false);
  }, []);

  useEffect(() => {
    // An address carrying a name the screens used to have opens the right screen, and is then written the way
    // the app writes it, so a link copied back out of the browser carries the name that is staying. Only on
    // arrival: `?admin` resolves its own hash, and replaceState fires no hashchange, so nothing loops.
    if (adminMode()) return;
    const canonical = canonicalHash(here().hash);
    if (canonical) rewrite(here().pathname + here().search + canonical);
  }, []);

  /** Leave an application: back to the Hive list, and take the join hash out of the address with it. */
  const leaveJoin = useCallback(() => {
    setJoining(null);
    setJoinHub("");
    setChoosing(true);
    // Hand our own pushed entry back to the browser, so the stack stays honest and forward still works. A
    // hash somebody pasted straight into the bar is not ours to pop, so that one is rewritten instead.
    if ((window.history.state as { join?: boolean } | null)?.join) window.history.back();
    else rewrite(here().pathname + here().search);
  }, []);

  // A reload, or a pasted link, arrives on a join hash with no directory row behind it. Resolve the id; a hub
  // that is no longer in the directory falls back to the list rather than to a blank screen.
  useEffect(() => {
    if (!joinHub || joining?.hub === joinHub) return;
    let gone = false;
    api
      .directory()
      .then((directory) => {
        if (gone) return;
        const row = directory.hubs.find((candidate) => candidate.hub === joinHub);
        if (row) setJoining(row);
        else leaveJoin();
      })
      .catch(() => !gone && leaveJoin());
    return () => {
      gone = true;
    };
  }, [joinHub, joining, leaveJoin]);

  useEffect(() => {
    // The address is the one source of truth for the view, so back and forward change what is on screen.
    const sync = () => {
      setAdmin(adminMode());
      setScreen(screenFromHash());
      setHub((chosen) => chosen || hubFromUrl() || chosenHub());
      // Including this one. An application used to outrank the router: the hash moved, the view did not, and
      // a reload was the only way out of it.
      const hash = here().hash;
      setJoinHub(joinHubIn(hash));
      if (namesScreen(hash)) {
        setChoosing(false);
        setJoining(null);
      }
    };
    // A screen opens at its top. The browser has just scrolled to the anchor, which sits under the sticky
    // header; a screen is not an anchor on a long page, so that jump is undone.
    const switched = () => {
      sync();
      window.scrollTo?.({ top: 0 });
    };
    window.addEventListener("popstate", sync);
    window.addEventListener("hashchange", switched);
    return () => {
      window.removeEventListener("popstate", sync);
      window.removeEventListener("hashchange", switched);
    };
  }, []);

  useEffect(() => {
    if (!admin) return;
    // A hash is one of the app's two screens and the panel has none of its own, so any hash while the panel is
    // open is in-app navigation: `#find` means "show me the finding screen", and now it does.
    const navigated = () => window.location.hash.length > 1 && leaveAdmin(true);
    window.addEventListener("hashchange", navigated);
    // A pasted `?admin#find` claims two views at once. It resolves to the panel, with the stray anchor dropped,
    // rather than rendering a hybrid nobody asked for.
    if (isHybrid(window.location.search, window.location.hash))
      rewrite(window.location.pathname + window.location.search);
    return () => window.removeEventListener("hashchange", navigated);
  }, [admin, leaveAdmin]);

  if (admin)
    return (
      <>
        <Header hub={hub} onHealth={setReached} onLeaveAdmin={() => leaveAdmin(false)} />
        <main>
          <AdminPanel onLeave={() => leaveAdmin(false)} />
        </main>
      </>
    );

  if (choosing || joinHub)
    return (
      <>
        <Header hub={hub} onHealth={setReached} />
        <main>
          {/* While a reload resolves the hub its hash names, the page is the header and nothing else: one
              round-trip, and the alternative is flashing the Hive list at somebody who asked for a form. */}
          {joinHub ? (
            joining && (
              <Onboarding
                hub={joining}
                onBack={leaveJoin}
                onUse={(picked) => {
                  const row = joining;
                  setChosenHub(picked, row && !row.home ? row.url || "" : "");
                  setJoining(null);
                  setJoinHub("");
                  setHub(picked);
                  setChoosing(false);
                  rewrite(here().pathname + here().search);
                }}
              />
            )
          ) : (
            <InstanceFinder
              onPick={(picked) => {
                setHub(picked);
                setChoosing(false);
                setReached(undefined);
              }}
              // Pushed, not replaced: the browser's back button is how most people cancel an application,
              // and before this it took them out of the app altogether.
              onJoin={(row) => {
                setJoining(row);
                setJoinHub(row.hub);
                history.pushState({ join: true }, "", here().pathname + here().search + joinHash(row.hub));
              }}
            />
          )}
        </main>
      </>
    );

  // Change Hive: drop the current pick, so the finder opens with nothing selected and the build's own backend.
  const changeHub = () => {
    forgetHub();
    setHub("");
    setReached(undefined);
    setChoosing(true);
  };

  // The finder turns the page to the business just booked: its owner sees the booking arrive.
  const openBusiness = (cardId: string) => {
    setBusiness(cardId);
    window.location.hash = "offer";
    window.scrollTo?.({ top: 0 });
  };

  return (
    <>
      <Header screen={screen} hub={hub} onHealth={setReached} />
      <main>
        {/* A chosen Hive that cannot be reached says so and offers the way back, rather than a dead page. */}
        {reached === false && (
          <p className="error hub-unreachable" role="status">
            {t("app.hubUnreachable")}{" "}
            <button className="quiet" onClick={changeHub}>
              {t("finder.change")}
            </button>
          </p>
        )}
        {/* Keyed by the hub and its URL, so picking a different one starts the page over against that backend. */}
        <div hidden={screen !== "find"}>
          <TravellerAgent key={`${hub}@${chosenHubUrl()}`} onOpenBusiness={openBusiness} />
        </div>
        <div hidden={screen !== "offer"}>
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
