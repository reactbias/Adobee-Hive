import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import en, { type Key } from "./en";
import de from "./de";
import fr from "./fr";
import it from "./it";

// Four languages for a Swiss audience. Strings live in one flat dictionary per locale; en.ts defines the keys and
// the other three must cover every one of them, or the build fails.
export const LOCALES = ["en", "de", "fr", "it"] as const;
export type Locale = (typeof LOCALES)[number];
export const LOCALE_NAMES: Record<Locale, string> = { en: "English", de: "Deutsch", fr: "Français", it: "Italiano" };

const DICTS: Record<Locale, Record<Key, string>> = { en, de, fr, it };
const STORAGE_KEY = "adobee-locale";

function initialLocale(): Locale {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved && (LOCALES as readonly string[]).includes(saved)) return saved as Locale;
  } catch {
    /* storage blocked: fall through to the browser language */
  }
  const wanted = typeof navigator !== "undefined" ? (navigator.languages ?? [navigator.language]) : [];
  for (const tag of wanted) {
    const base = tag.slice(0, 2).toLowerCase();
    if ((LOCALES as readonly string[]).includes(base)) return base as Locale;
  }
  return "en";
}

/** Every translation of a key, to recognise untouched sample text when the language changes. */
export const allLocales = (key: Key): string[] => LOCALES.map((l) => DICTS[l][key]);

export type Vars = Record<string, string | number>;

interface I18n {
  locale: Locale;
  setLocale: (l: Locale) => void;
  t: (key: Key, vars?: Vars) => string;
  /** BCP 47 tag with Swiss conventions, for Intl formatting. */
  intl: string;
}

const Ctx = createContext<I18n | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(initialLocale);

  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);

  const setLocale = useCallback((l: Locale) => {
    setLocaleState(l);
    try {
      localStorage.setItem(STORAGE_KEY, l);
    } catch {
      /* the choice just won't survive a reload */
    }
  }, []);

  const value = useMemo<I18n>(() => {
    const dict = DICTS[locale];
    const t = (key: Key, vars?: Vars) => {
      const s = dict[key] ?? en[key];
      return vars ? s.replace(/\{(\w+)\}/g, (_, k: string) => String(vars[k] ?? `{${k}}`)) : s;
    };
    return { locale, setLocale, t, intl: `${locale}-CH` };
  }, [locale, setLocale]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/**
 * State seeded with sample text that follows the language switch until the user edits it.
 * `keys` lists the samples it may hold; the first one is the initial value.
 */
export function useSample(keys: Key[]): [string, (v: string) => void] {
  const { t } = useI18n();
  const [value, setValue] = useState(() => t(keys[0]));
  useEffect(() => {
    setValue((cur) => {
      const hit = keys.find((k) => allLocales(k).includes(cur));
      return hit ? t(hit) : cur;
    });
    // Re-run only on a language change; keys is a constant list per call site.
  }, [t]);
  return [value, setValue];
}

export function useI18n(): I18n {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("useI18n outside I18nProvider");
  return ctx;
}
