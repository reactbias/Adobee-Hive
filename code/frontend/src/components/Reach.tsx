import { useI18n } from "../i18n";
import type { Key } from "../i18n/en";
import Icon from "./Icon";

// How far a search goes: this Hive only, its neighbours, or further. The number is the discover radius.

const STEPS: { radius: number; label: Key }[] = [
  { radius: 0, label: "reach.local" },
  { radius: 1, label: "reach.near" },
  { radius: 3, label: "reach.far" },
];

export default function Reach({
  radius,
  disabled = false,
  onChange,
}: {
  radius: number;
  disabled?: boolean;
  onChange: (radius: number) => void;
}) {
  const { t } = useI18n();
  return (
    <div className="reach">
      <span className="eyebrow">
        <Icon name="hive" size={24} /> {t("reach.label")}
      </span>
      <div className="tabs reach-steps" role="radiogroup" aria-label={t("reach.label")}>
        {STEPS.map((step) => (
          <button
            key={step.radius}
            role="radio"
            aria-checked={radius === step.radius}
            className={radius === step.radius ? "tab on" : "tab"}
            disabled={disabled}
            onClick={() => onChange(step.radius)}
          >
            {t(step.label)}
          </button>
        ))}
      </div>
    </div>
  );
}
