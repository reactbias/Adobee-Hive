// Which scheme the page is in, and who decided.
//
// Three states, because "dark mode on/off" cannot say the true default: most readers want whatever their
// operating system is doing, and that changes under them at sunset. So `system` is a state of its own and is
// what an address with nothing stored uses — it is not light wearing a different name.
//
// Only an explicit choice is stored. Choosing `system` removes the key rather than writing "system", so a
// reader who never touches the control is never pinned to the scheme their laptop happened to be in.

export type Theme = "system" | "light" | "dark";

export const THEMES: Theme[] = ["system", "light", "dark"];

const KEY = "adobee-theme";

/** The stored choice, or `system` when there is none. */
export function storedTheme(): Theme {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    /* storage blocked: follow the operating system, as if nothing had been chosen */
  }
  return "system";
}

/**
 * Put the choice on `<html>`, which is the hook the stylesheet already reads.
 *
 * `system` means *no* attribute: the stylesheet's `@media (prefers-color-scheme: dark)` rule is guarded with
 * `:not([data-theme="light"])`, so an absent attribute lets the operating system through, and the browser
 * re-evaluates that media query by itself when the OS changes. There is nothing to subscribe to and nothing
 * to re-apply — the one case a hand-rolled listener usually gets wrong is the one CSS already handles.
 */
export function applyTheme(theme: Theme) {
  const root = document.documentElement;
  if (theme === "system") root.removeAttribute("data-theme");
  else root.setAttribute("data-theme", theme);
}

/** Remember an explicit choice; forget it again when the reader goes back to following the system. */
export function storeTheme(theme: Theme) {
  try {
    if (theme === "system") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, theme);
  } catch {
    /* the choice lasts as long as this page does */
  }
}

/** Which scheme is actually on screen, for a label that has to say what "Automatic" currently means. */
export function resolvedTheme(theme: Theme = storedTheme()): "light" | "dark" {
  if (theme !== "system") return theme;
  return window.matchMedia?.("(prefers-color-scheme: dark)")?.matches ? "dark" : "light";
}
