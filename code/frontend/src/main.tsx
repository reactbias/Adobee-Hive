import React, { useEffect, useState } from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, NavLink, Route, Routes } from "react-router-dom";
import { api, type Health } from "./api";
import Home from "./pages/Home";
import TravellerAgent from "./pages/TravellerAgent";
import OwnerStudio from "./pages/OwnerStudio";
import CardPage from "./pages/CardPage";
import DemandMap from "./pages/DemandMap";
import B6Bee from "./components/B6Bee";
import "./styles.css";

function Nav() {
  const [health, setHealth] = useState<Health | null>(null);
  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
  }, []);
  const link = ({ isActive }: { isActive: boolean }) => `link${isActive ? " active" : ""}`;
  return (
    <nav className="nav">
      <NavLink to="/" className="brand">
        <img src="/brand/logo.svg" alt="" width={36} height={36} /> Adobee Hive
      </NavLink>
      <NavLink to="/agent" className={link}>Traveller agent</NavLink>
      <NavLink to="/owner" className={link}>Owner studio</NavLink>
      <NavLink to="/demand" className={link}>Demand map</NavLink>
      <span className="mode" title={health ? `${health.model} / ${health.fast_model}` : "backend unreachable"}>
        {health ? (health.llm === "claude" ? "Claude live" : "offline mode") : "backend down"}
      </span>
    </nav>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
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
  </React.StrictMode>,
);
