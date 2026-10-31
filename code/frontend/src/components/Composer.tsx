import { useEffect, useLayoutEffect, useRef, type ReactNode, type RefObject } from "react";
import MicButton from "./MicButton";

/** About eight lines of request text; past that the box scrolls instead of growing. */
const MAX_BOX_PX = 300;

// The one input every agent on the page listens to: a box that sends on Enter, a microphone, a send button that
// says when the agent is working, and a Try list of examples that send with one tap.

export default function Composer({
  id,
  label,
  value,
  onChange,
  onSend,
  busy,
  sendLabel,
  busyLabel,
  placeholder,
  tryLabel,
  examples = [],
  secondary,
  boxRef,
  maxLength,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (text: string) => void;
  /** Called with the trimmed text. */
  onSend: (text: string) => void;
  busy: boolean;
  sendLabel: string;
  busyLabel: string;
  placeholder?: string;
  tryLabel?: string;
  /** Example requests, already translated; hidden when empty. */
  examples?: string[];
  /** A quiet action left of the microphone, such as New trip. */
  secondary?: ReactNode;
  boxRef?: RefObject<HTMLTextAreaElement>;
  maxLength?: number;
}) {
  const own = useRef<HTMLTextAreaElement>(null);
  const box = boxRef ?? own;

  // The box grows with its text, so the whole request is always in view, in any language.
  const fit = () => {
    const el = box.current;
    if (!el) return;
    el.style.height = "auto";
    const needed = el.scrollHeight;
    if (!needed) {
      el.style.removeProperty("height");
      return;
    }
    el.style.height = `${Math.min(needed, MAX_BOX_PX)}px`;
    el.style.overflowY = needed > MAX_BOX_PX ? "auto" : "hidden";
  };
  useLayoutEffect(() => fit(), [value]);
  useEffect(() => {
    window.addEventListener("resize", fit);
    return () => window.removeEventListener("resize", fit);
  }, []);

  const send = (text = value) => {
    if (text.trim() && !busy) onSend(text.trim());
  };
  return (
    <>
      <div className="composer">
        <label htmlFor={id}>{label}</label>
        <textarea
          id={id}
          ref={box}
          value={value}
          maxLength={maxLength}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            // Enter sends, as in any chat; Shift+Enter is a new line. Not while an IME is composing.
            if (e.key !== "Enter" || e.shiftKey || e.nativeEvent.isComposing) return;
            e.preventDefault();
            send();
          }}
          placeholder={placeholder}
        />
        <div className="composer-bar">
          <span className="composer-actions">
            {secondary}
            <MicButton value={value} onChange={onChange} disabled={busy} />
            <button className={busy ? "busy" : ""} onClick={() => send()} disabled={busy || !value.trim()}>
              {busy ? busyLabel : sendLabel}
            </button>
          </span>
        </div>
      </div>
      {examples.length > 0 && (
        <div className="examples">
          {tryLabel && <span className="eyebrow">{tryLabel}</span>}
          <ul className="rows compact">
            {examples.map((text) => (
              <li key={text}>
                <button className="example" onClick={() => send(text)} disabled={busy}>
                  {text}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}
