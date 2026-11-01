import { useEffect, useState } from "react";
import { useI18n } from "../i18n";
import type { Key } from "../i18n/en";
import { applyTheme, storedTheme, storeTheme, THEMES, type Theme } from "../lib/theme";

const LABEL: Record<Theme, Key> = {
  system: "theme.system",
  light: "theme.light",
  dark: "theme.dark",
};

/**
 * Light, dark, or whatever the reader's system is doing. Three states, beside the language buttons, because
 * the honest default is not a scheme but a deferral: follow the system until somebody says otherwise.
 */
export default function ThemeToggle() {
  const { t } = useI18n();
  const [theme, setTheme] = useState<Theme>(storedTheme);

  // On arrival the inline script in index.html has already set the attribute, so this agrees with it rather
  // than racing it. It matters on a soft navigation, and when storage was blocked and the script wrote nothing.
  useEffect(() => applyTheme(theme), [theme]);

  const choose = (next: Theme) => {
    storeTheme(next);
    setTheme(next);
  };

  return (
    <div className="themes" role="radiogroup" aria-label={t("theme.label")}>
      {THEMES.map((option) => (
        <button
          key={option}
          role="radio"
          aria-checked={theme === option}
          className={theme === option ? "on" : ""}
          title={t(LABEL[option])}
          aria-label={t(LABEL[option])}
          onClick={() => choose(option)}
        >
          {option === "system" ? "◐" : option === "light" ? "☀" : "☾"}
        </button>
      ))}
    </div>
  );
}
