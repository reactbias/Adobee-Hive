import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "../i18n";
import en from "../i18n/en";
import GroupChat, { type Segment } from "./GroupChat";

// When the agents start talking the chat follows the newest message, unless the reader scrolled up to reread:
// then it stays put and offers a way back down.

const SEGMENTS: Segment[] = [
  { kind: "guest", text: "A quiet room, please." },
  { kind: "ack" },
  { kind: "agent", text: "First line from the agent." },
  { kind: "agent", text: "Second line from the agent." },
  { kind: "agent", text: "Third line from the agent." },
];

function setup(segments = SEGMENTS) {
  localStorage.setItem("adobee-locale", "en");
  const view = render(
    <I18nProvider>
      <GroupChat segments={segments} guestName="Mara" pending={false} meta={null} />
    </I18nProvider>,
  );
  const el = view.container.querySelector(".chat-scroll") as HTMLDivElement;
  // jsdom has no layout: give the scroller a size, and remember where the reader is.
  Object.defineProperty(el, "scrollHeight", { configurable: true, value: 1000 });
  Object.defineProperty(el, "clientHeight", { configurable: true, value: 400 });
  return el;
}

const userScrollsTo = (el: HTMLElement, top: number) => {
  el.scrollTop = top;
  fireEvent.scroll(el);
};

describe("group chat scrolling", () => {
  let scrollTo: ReturnType<typeof vi.fn>;
  beforeEach(() => {
    vi.useFakeTimers();
    scrollTo = vi.fn();
    Element.prototype.scrollTo = scrollTo as unknown as typeof Element.prototype.scrollTo;
  });
  afterEach(() => vi.useRealTimers());

  it("follows the newest message while the reader is at the bottom", () => {
    setup();
    scrollTo.mockClear();
    act(() => vi.advanceTimersByTime(3000));
    expect(scrollTo).toHaveBeenCalledWith(expect.objectContaining({ top: 1000 }));
  });

  it("stops following once the reader scrolls up, and offers a way back", () => {
    const el = setup();
    act(() => vi.advanceTimersByTime(2000));
    userScrollsTo(el, 600);
    userScrollsTo(el, 150);
    scrollTo.mockClear();

    act(() => vi.advanceTimersByTime(20000));
    expect(scrollTo).not.toHaveBeenCalled();

    const back = screen.getByRole("button", { name: en["chat.latest"] });
    fireEvent.click(back);
    expect(scrollTo).toHaveBeenCalledWith(expect.objectContaining({ top: 1000 }));
    expect(screen.queryByRole("button", { name: en["chat.latest"] })).not.toBeInTheDocument();
  });

  it("follows again when the reader scrolls back to the bottom", () => {
    const el = setup();
    act(() => vi.advanceTimersByTime(1500));
    userScrollsTo(el, 600);
    userScrollsTo(el, 100);
    userScrollsTo(el, 590);
    scrollTo.mockClear();
    act(() => vi.advanceTimersByTime(20000));
    expect(scrollTo).toHaveBeenCalled();
  });
});

// A request no card covers gets an honest answer: nobody offers it yet, and the critic says why no card was forced.
describe("a request no card covers", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("says so instead of showing the nearest card", () => {
    const result = {
      question: "book me a taxi",
      preference: { mood: null, effects: [], source: "chosen by you" },
      replies: [],
      excluded: [],
      budget_chf: null,
      rate: null,
      pending: null,
      rules: [],
      answer: null,
      mode: "offline",
      unserved: true,
      relevance: { by: "offline", reason: null },
    };
    setup([{ kind: "guest", text: "book me a taxi" }, { kind: "ack" }, { kind: "ask", result }]);
    for (let i = 0; i < 40; i++) act(() => vi.advanceTimersByTime(1000));
    expect(screen.getByText(en["ask.empty"])).toBeInTheDocument();
    expect(screen.getByText(en["chat.ask.uncovered"])).toBeInTheDocument();
  });
});

describe("saying yes to a hand-off", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("reads as going to the business's site, not as a booking", () => {
    setup([
      { kind: "guest", text: "Pax please" },
      { kind: "consent", handoff: true },
    ]);
    for (let i = 0; i < 10; i++) act(() => vi.advanceTimersByTime(1000));
    expect(screen.getByText(en["ask.pending.approve"])).toBeInTheDocument();
    expect(screen.queryByText(en["chat.guest.yes"])).not.toBeInTheDocument();
  });
});
