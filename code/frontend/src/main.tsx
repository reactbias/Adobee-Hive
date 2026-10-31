import React, { useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";
import { api, type Health } from "./api";
import { I18nProvider, LOCALES, LOCALE_NAMES, useI18n, type Locale } from "./i18n";
import Home from "./pages/Home";
import TravellerAgent from "./pages/TravellerAgent";
import OwnerStudio from "./pages/OwnerStudio";
import CardPage from "./pages/CardPage";
import DemandMap from "./pages/DemandMap";
import B6Bee from "./components/B6Bee";
import "./styles.css";

function Nav() {
  const { t, locale, setLocale } = useI18n();
  const [health, setHealth] = useState<Health | null | undefined>(undefined);
  useEffect(() => {
    api
      .health()
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);
  const link = ({ isActive }: { isActive: boolean }) => `link${isActive ? " active" : ""}`;
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
        <NavLink to="/" className="brand">
          <img src={`${import.meta.env.BASE_URL}brand/logo.svg`} alt="" width={30} height={30} />
          <span>Adobee Hive</span>
        </NavLink>
        <div className="nav-links">
          <NavLink to="/agent" className={link}>
            {t("nav.agent")}
          </NavLink>
          <NavLink to="/owner" className={link}>
            {t("nav.owner")}
          </NavLink>
          <NavLink to="/demand" className={link}>
            {t("nav.demand")}
          </NavLink>
        </div>
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

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <I18nProvider>
      <BrowserRouter basename={import.meta.env.BASE_URL}>
        <Nav />
        <main>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/agent" element={<TravellerAgent />} />
            <Route path="/owner" element={<OwnerStudio />} />
            <Route path="/card/:slug" element={<CardPage />} />
            <Route path="/demand" element={<DemandMap />} />
          </Routes>
        </main>
        <B6Bee />
      </BrowserRouter>
    </I18nProvider>
  </React.StrictMode>,
);
