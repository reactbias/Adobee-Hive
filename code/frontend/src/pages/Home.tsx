import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, mcpUrl, type Card } from "../api";
import TrustBadge from "../components/TrustBadge";

export default function Home() {
  const [cards, setCards] = useState<Card[]>([]);
  useEffect(() => {
    api
      .cards()
      .then(setCards)
      .catch(() => setCards([]));
  }, []);

  return (
    <>
      <section className="hero">
        <div>
          <h1>The website is not the front door anymore.</h1>
          <p className="lead">
            The first visitor of a Basel hotel is increasingly an AI agent. Adobee Hive gives every local business a
            signed, agent-readable card that agents can search, trust and book through, and that the owner edits in
            plain words. One presence serves agents and humans, and nothing is booked until a person says yes.
          </p>
          <div className="row">
            <Link className="btn" to="/agent">
              Watch two agents negotiate
            </Link>
            <Link className="btn" to="/owner" style={{ background: "transparent" }}>
              I own a business
            </Link>
          </div>
        </div>
        <figure className="hero-logo">
          <img src="/brand/logo.svg" alt="Adobee Hive: a clay-brick hexagon with a bee inside" />
          <figcaption>
            On GitHub you find projects to work on. On Adobee Hive, agents find businesses and people to work with.
          </figcaption>
        </figure>
      </section>

      <section className="grid three" style={{ marginBottom: 28 }}>
        <div className="panel">
          <h3>Provenance, not promises</h3>
          <p className="muted">
            Each card version is signed with the owner's Ed25519 key. Agents verify it themselves, and third parties
            attest single claims.
          </p>
        </div>
        <div className="panel">
          <h3>Proof-of-stay reviews</h3>
          <p className="muted">
            Only a guest holding a signed booking receipt can review. No receipt, no review, no review farms.
          </p>
        </div>
        <div className="panel">
          <h3>Fair, explainable ranking</h3>
          <p className="muted">
            Agents get the score breakdown and the reasons a business was left out. Owners see that missed demand. No
            paid boosts.
          </p>
        </div>
      </section>

      <h2>In the Hive today</h2>
      <p className="muted">
        Agents connect at <code>{mcpUrl()}</code> (MCP, Streamable HTTP). Add it to Claude or any MCP client.
      </p>
      <div className="grid three">
        {cards.map((c) => (
          <Link key={c.id} to={`/card/${c.slug}`} className="panel" style={{ textDecoration: "none" }}>
            <span className="chip">{c.kind}</span>
            <h3>{c.name}</h3>
            <p className="muted">{c.tagline}</p>
            <TrustBadge trust={c.trust} />
          </Link>
        ))}
      </div>
    </>
  );
}
