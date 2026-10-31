import { type DirectoryHub, type Peer } from "../api";
import { useI18n } from "../i18n";
import type { Key } from "../i18n/en";
import { readCalibration, stars } from "../lib/calibration";

/**
 * Calibration, labelled: lower is better, and a negative error means the hub undersold what it offered.
 *
 * Shared by the admin panel's peer table and anything else that shows a hub next to its standing, so the
 * wording of the one number that matters about a peer is written once.
 */
export default function Calibration({ peer }: { peer: Peer | DirectoryHub }) {
  const { t, intl } = useI18n();
  const { reading, stars: n } = readCalibration(peer.error, peer.verdict);
  if (reading === "unproven") return <span className="status">{t("finder.cal.unproven")}</span>;
  return (
    <span className={`status ${reading === "over" ? "no" : "ok"}`}>
      {t(`finder.cal.${reading}` as Key, { stars: stars(n, intl) })}
    </span>
  );
}
