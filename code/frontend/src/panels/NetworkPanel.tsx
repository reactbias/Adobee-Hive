import { useCallback, useEffect, useRef, useState } from "react";
import { api, type AdminNeighbours, type AdminOverview, type Directory } from "../api";
import { useI18n } from "../i18n";
import type { Key } from "../i18n/en";
import { readCalibration, stars } from "../lib/calibration";
import { buildNetwork, clip, hexPoints, liveIntroductions, ringPosition, viewBox, type HubNode } from "../lib/network";

// The hub network as it is right now, not as a diagram: this hub in the centre of a honeycomb, each configured
// peer a cell around it. Hexagons because the logo is a bee in an open hexagon and the cell is the shape the
// brand is built on. Hand-drawn SVG, no charting dependency.
//
// Open to anyone: a federated network that only its operator can see the shape of is not a federated network.
// Everything comes from endpoints already on `main`; the directory (PR #71) only adds names and entity counts,
// and its absence shows as unknown rather than as zero.

const CX = 300;
const CY = 210;
const HOME_R = 62;
const PEER_R = 44;
// How many characters fit inside a cell at its font size, measured by eye at 13 px semibold.
const HOME_CHARS = 14;
const PEER_CHARS = 11;
const POLL_MS = 10_000;

const ADMISSIONS = ["open", "vetted", "invite", "closed"];

/** Which way a peer's calibration goes, as a class: clay for held or beaten, red for over-promised, grey for thin. */
function edgeClass(node: HubNode): string {
  if (node.blocked) return "cut";
  const { reading } = readCalibration(node.error, node.verdict);
  return reading === "over" ? "over" : reading === "unproven" ? "unproven" : "kept";
}

/** One line of calibration, in words, never a bare number that could read as a score. */
function CalibrationLine({ node }: { node: HubNode }) {
  const { t, intl } = useI18n();
  const { reading, stars: n } = readCalibration(node.error, node.verdict);
  if (reading === "unproven") return <span className="status">{t("finder.cal.unproven")}</span>;
  return (
    <span className={`status ${reading === "over" ? "no" : "ok"}`}>
      {t(`finder.cal.${reading}` as Key, { stars: stars(n, intl) })}
    </span>
  );
}

/** One hexagon cell. The full name is in a `title`, because the drawn one is clipped to fit the cell. */
function Cell({ node, x, y, r }: { node: HubNode; x: number; y: number; r: number }) {
  const { t } = useI18n();
  const cell = ["net-cell", node.home ? "home" : "peer", node.blocked ? "blocked" : ""].join(" ");
  return (
    <g className={cell}>
      <title>{node.label}</title>
      <polygon points={hexPoints(x, y, r)} />
      <text x={x} y={y - (node.home ? 6 : 5)} className="net-label">
        {clip(node.label, node.home ? HOME_CHARS : PEER_CHARS)}
      </text>
      <text x={x} y={y + (node.home ? 14 : 11)} className="net-sub">
        {node.entities === null ? t("network.unknownShort") : t("network.entitiesShort", { n: node.entities })}
      </text>
    </g>
  );
}

/** The mark on a blocked edge: a cut, so the peer is still shown and plainly not connected. */
function Cut({ x, y }: { x: number; y: number }) {
  return (
    <g className="net-cut">
      <circle cx={x} cy={y} r={11} />
      <line x1={x - 5} y1={y - 5} x2={x + 5} y2={y + 5} />
      <line x1={x + 5} y1={y - 5} x2={x - 5} y2={y + 5} />
    </g>
  );
}

/** The picture. Separate from the fetching so it can be reasoned about, and drawn from nodes alone. */
function Honeycomb({ nodes }: { nodes: HubNode[] }) {
  const { t } = useI18n();
  const [home, ...peers] = nodes;
  const placed = peers.map((node, i) => ({ node, ...ringPosition(i, peers.length, CX, CY) }));
  // Drawn tight around what is there: a hub with no peers yet is one cell, not one cell lost in white space.
  const box = viewBox(placed, CX, CY, (placed.length ? PEER_R : HOME_R) + 18);
  const [, , w, h] = box.split(" ").map(Number);
  return (
    // Width and height as attributes, so a hub with no peers draws at its own size instead of being blown up
    // to fill the column. The stylesheet only caps it.
    <svg className="net-map" viewBox={box} width={w} height={h} role="img" aria-labelledby="net-map-title">
      <title id="net-map-title">{t("network.diagram")}</title>
      <g className="net-edges">
        {placed.map(({ node, x, y }) => (
          <g key={node.hub} className={`net-edge ${edgeClass(node)}`}>
            <line x1={CX} y1={CY} x2={x} y2={y} />
            {node.blocked && <Cut x={CX + (x - CX) * 0.62} y={CY + (y - CY) * 0.62} />}
          </g>
        ))}
      </g>
      {placed.map(({ node, x, y }) => (
        <Cell key={node.hub} node={node} x={x} y={y} r={PEER_R} />
      ))}
      <Cell node={home} x={CX} y={CY} r={HOME_R} />
    </svg>
  );
}

/** The same hubs as rows: the honest detail, and what a phone shows instead of a squashed graph. */
function Rows({ nodes }: { nodes: HubNode[] }) {
  const { t } = useI18n();
  return (
    <ul className="rows net-rows" aria-label={t("network.hubs")}>
      {nodes.map((node) => (
        <li key={node.hub}>
          <span className="stack tight">
            <strong>{node.label}</strong>
            <span className="muted small">
              {node.home ? t("network.thisHub") : node.blocked ? t("network.blockedHub") : node.why}
            </span>
          </span>
          <span className="stack tight net-row-end">
            <span className="muted small">
              {node.entities === null ? t("network.entitiesUnknown") : t("network.entities", { n: node.entities })}
              {" · "}
              {ADMISSIONS.includes(node.admission)
                ? t(`finder.admission.${node.admission}` as Key)
                : t("network.admissionUnknown")}
            </span>
            {!node.home && <CalibrationLine node={node} />}
          </span>
        </li>
      ))}
    </ul>
  );
}

/**
 * The live network, for anyone: four counts, the honeycomb, then the same hubs as rows. Polls every 10 s, and
 * only while it is on screen and the tab is in front.
 */
export default function NetworkPanel() {
  const { t } = useI18n();
  const [overview, setOverview] = useState<AdminOverview | null>(null);
  const [neighbours, setNeighbours] = useState<AdminNeighbours | null>(null);
  const [directory, setDirectory] = useState<Directory | null>(null);
  const [reached, setReached] = useState<boolean | null>(null);
  const section = useRef<HTMLElement>(null);
  const onScreen = useRef(true);

  const load = useCallback(() => {
    api
      .adminOverview()
      .then((o) => {
        setOverview(o);
        setReached(true);
      })
      .catch(() => setReached(false));
    // A configured peer that does not answer still has a row here; the directory is simply not on `main` yet.
    api
      .adminNeighbours()
      .catch(() => ({ peers: [], blocked_hubs: [] }) as AdminNeighbours)
      .then(setNeighbours);
    api
      .directory()
      .catch(() => null)
      .then(setDirectory);
  }, []);

  useEffect(() => {
    load();
    const watch =
      typeof IntersectionObserver === "undefined"
        ? null
        : new IntersectionObserver(([e]) => (onScreen.current = e.isIntersecting));
    if (watch && section.current) watch.observe(section.current);
    const timer = setInterval(() => {
      if (onScreen.current && !document.hidden) load();
    }, POLL_MS);
    return () => {
      clearInterval(timer);
      watch?.disconnect();
    };
  }, [load]);

  const nodes = buildNetwork(overview, neighbours, directory);
  const counts: [Key, number][] = [
    ["network.count.entities", overview?.index.entities ?? 0],
    ["network.count.peers", nodes.length - 1],
    ["network.count.live", liveIntroductions(overview)],
    ["network.count.blocked", (overview?.blocklist.hubs ?? 0) + (overview?.blocklist.entities ?? 0)],
  ];

  return (
    <section className="network" id="network" ref={section}>
      <div className="network-inner stack loose">
        <div className="stack tight">
          <p className="eyebrow">{t("network.eyebrow")}</p>
          <h2>{t("network.title")}</h2>
          <p className="muted">{t("network.lead")}</p>
        </div>
        {reached === false && <p className="error">{t("network.unreachable")}</p>}
        <ul className="net-counts">
          {counts.map(([key, n]) => (
            <li key={key}>
              <strong className="num">{reached === null ? "–" : n}</strong>
              <span className="muted small">{t(key)}</span>
            </li>
          ))}
        </ul>
        <Honeycomb nodes={nodes} />
        {nodes.length === 1 && <p className="muted">{t("network.alone")}</p>}
        <Rows nodes={nodes} />
        <p className="muted small">{t("network.legend")}</p>
      </div>
    </section>
  );
}
