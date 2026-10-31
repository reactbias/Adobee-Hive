import { useI18n } from "../i18n";
import type { Key } from "../i18n/en";
import Icon, { type IconName } from "./Icon";

// The four promises, by their brand names and in the brand's order (BRAND.md): one icon, one name, one line each.
const PRINCIPLES: { id: string; icon: IconName }[] = [
  { id: "signed", icon: "seal" },
  { id: "ranking", icon: "rank" },
  { id: "stay", icon: "receipt" },
  { id: "yes", icon: "yes" },
];

/** The strip between the two chapters: what a traveller and a business can both count on. */
export default function Principles() {
  const { t } = useI18n();
  return (
    <section className="principles" aria-label={t("principles.label")}>
      <ul className="principles-list" aria-label={t("principles.label")}>
        {PRINCIPLES.map((p) => (
          <li key={p.id}>
            <Icon name={p.icon} size={24} />
            <h3>{t(`principles.${p.id}.title` as Key)}</h3>
            <p>{t(`principles.${p.id}.body` as Key)}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
