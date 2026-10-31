import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "../i18n";
import de from "../i18n/de";
import en from "../i18n/en";
import MicButton from "./MicButton";

// Speech input runs on the browser's own Web Speech API: no key, no service of ours. Where the browser has none
// (Firefox), the button is simply not there.

type Handler = ((e: unknown) => void) | null;

class FakeRecognition {
  static last: FakeRecognition;
  lang = "";
  interimResults = false;
  continuous = false;
  onresult: Handler = null;
  onerror: Handler = null;
  onend: Handler = null;
  start = vi.fn();
  stop = vi.fn(() => this.onend?.({}));
  abort = vi.fn();
  constructor() {
    FakeRecognition.last = this;
  }
}

const said = (...parts: [string, boolean][]) => ({
  resultIndex: 0,
  results: parts.map(([transcript, isFinal]) => Object.assign([{ transcript }], { isFinal })),
});

function setup(value = "", locale = "en") {
  localStorage.setItem("adobee-locale", locale);
  const onChange = vi.fn();
  render(
    <I18nProvider>
      <MicButton value={value} onChange={onChange} />
    </I18nProvider>,
  );
  return { onChange, user: userEvent.setup() };
}

describe("speech input", () => {
  beforeEach(() => {
    delete (window as unknown as Record<string, unknown>).SpeechRecognition;
    delete (window as unknown as Record<string, unknown>).webkitSpeechRecognition;
  });
  afterEach(() => {
    delete (window as unknown as Record<string, unknown>).webkitSpeechRecognition;
  });

  it("is hidden where the browser cannot listen", () => {
    setup();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("listens in the page's language and writes what was said into the request", async () => {
    (window as unknown as Record<string, unknown>).webkitSpeechRecognition = FakeRecognition;
    const { onChange, user } = setup("Basel,", "de");

    await user.click(screen.getByRole("button", { name: de["mic.start"] }));
    const rec = FakeRecognition.last;
    expect(rec.start).toHaveBeenCalled();
    expect(rec.lang).toBe("de-CH");
    expect(screen.getByRole("button", { name: de["mic.stop"] })).toHaveAttribute("aria-pressed", "true");

    act(() => rec.onresult?.(said(["ruhiges Hotel", false])));
    expect(onChange).toHaveBeenLastCalledWith("Basel, ruhiges Hotel");
    act(() => rec.onresult?.(said(["ruhiges Hotel mit Hund", true])));
    expect(onChange).toHaveBeenLastCalledWith("Basel, ruhiges Hotel mit Hund");

    act(() => rec.onend?.({}));
    expect(screen.getByRole("button", { name: de["mic.start"] })).toHaveAttribute("aria-pressed", "false");
  });

  it("stops on a second tap", async () => {
    (window as unknown as Record<string, unknown>).webkitSpeechRecognition = FakeRecognition;
    const { user } = setup();
    await user.click(screen.getByRole("button", { name: en["mic.start"] }));
    await user.click(screen.getByRole("button", { name: en["mic.stop"] }));
    expect(FakeRecognition.last.stop).toHaveBeenCalled();
    expect(screen.getByRole("button", { name: en["mic.start"] })).toBeInTheDocument();
  });

  it("says so when the microphone is blocked", async () => {
    (window as unknown as Record<string, unknown>).webkitSpeechRecognition = FakeRecognition;
    const { user } = setup();
    await user.click(screen.getByRole("button", { name: en["mic.start"] }));
    act(() => {
      FakeRecognition.last.onerror?.({ error: "not-allowed" });
      FakeRecognition.last.onend?.({});
    });
    expect(screen.getByRole("button", { name: en["mic.blocked"] })).toBeInTheDocument();
  });

  it("uses British English for English", async () => {
    (window as unknown as Record<string, unknown>).webkitSpeechRecognition = FakeRecognition;
    const { user } = setup();
    await user.click(screen.getByRole("button", { name: en["mic.start"] }));
    expect(FakeRecognition.last.lang).toBe("en-GB");
  });
});
