import { useEffect, useRef, useState } from "react";
import { useI18n } from "../i18n";

// Speak a request instead of typing it. This is the browser's own Web Speech API: no key and no service of ours.
// Chrome and Edge send the audio to their vendor's recogniser, Safari listens on the device; Firefox has none, so
// there the button is not shown at all.

interface Alternative {
  transcript: string;
}
interface Result extends ArrayLike<Alternative> {
  isFinal: boolean;
}
interface Recognition {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((e: { results: ArrayLike<Result> }) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}
type RecognitionClass = new () => Recognition;

/** The browser's recogniser, under either name, or null where there is none. */
export function recogniser(): RecognitionClass | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as Record<string, RecognitionClass | undefined>;
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

/** A recogniser language for the page's language; Swiss variants, British English. */
export const speechLang = (locale: string) => (locale === "en" ? "en-GB" : `${locale}-CH`);

/** A microphone toggle that writes what was said after the text already in the box. */
export default function MicButton({
  value,
  onChange,
  disabled = false,
}: {
  value: string;
  onChange: (text: string) => void;
  disabled?: boolean;
}) {
  const { t, locale } = useI18n();
  const [listening, setListening] = useState(false);
  const [blocked, setBlocked] = useState(false);
  const rec = useRef<Recognition | null>(null);
  const Recogniser = recogniser();

  // Leaving the page or switching it off mid-sentence stops the microphone.
  useEffect(() => () => rec.current?.abort(), []);

  if (!Recogniser) return null;

  function start() {
    const r = new Recogniser!();
    const base = value.trim();
    r.lang = speechLang(locale);
    r.interimResults = true;
    r.continuous = false;
    r.onresult = (e) => {
      const heard = Array.from(e.results, (res) => res[0]?.transcript ?? "")
        .join("")
        .trim();
      onChange([base, heard].filter(Boolean).join(" "));
    };
    r.onerror = (e) => {
      if (e.error === "not-allowed" || e.error === "service-not-allowed") setBlocked(true);
    };
    r.onend = () => {
      setListening(false);
      rec.current = null;
    };
    rec.current = r;
    setBlocked(false);
    setListening(true);
    r.start();
  }

  function stop() {
    rec.current?.stop();
    setListening(false);
  }

  const label = listening ? t("mic.stop") : blocked ? t("mic.blocked") : t("mic.start");
  return (
    <button
      type="button"
      className={`mic${listening ? " listening" : ""}${blocked ? " blocked" : ""}`}
      aria-pressed={listening}
      aria-label={label}
      title={label}
      disabled={disabled && !listening}
      onClick={listening ? stop : start}
    >
      <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden>
        <path d="M12 3.5a2.8 2.8 0 0 1 2.8 2.8v5.4a2.8 2.8 0 0 1-5.6 0V6.3A2.8 2.8 0 0 1 12 3.5Z" />
        <path d="M6.5 11.2a5.5 5.5 0 0 0 11 0M12 16.7v3.8M9 20.5h6" />
        {blocked && <path d="M4.5 19.5l15-15" />}
      </svg>
      {listening && <span className="mic-live">{t("mic.listening")}</span>}
    </button>
  );
}
