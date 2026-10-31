import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "../i18n";
import en from "../i18n/en";
import Composer from "./Composer";

// One input for every agent on the page: the same box, hint, microphone, send button and Try list.

function Harness(props: { onSend: (text: string) => void; busy?: boolean; start?: string; bar?: boolean }) {
  const [value, setValue] = useState(props.start ?? "");
  return (
    <Composer
      id="box"
      label={en["agent.intent"]}
      value={value}
      onChange={setValue}
      onSend={props.onSend}
      busy={props.busy ?? false}
      sendLabel={en["agent.send"]}
      busyLabel={en["agent.sending"]}
      tryLabel={en["agent.try"]}
      examples={[en["agent.example.2"], en["agent.example.3"]]}
      bar={props.bar}
    />
  );
}

function setup(props: Parameters<typeof Harness>[0]) {
  render(
    <I18nProvider>
      <Harness {...props} />
    </I18nProvider>,
  );
  return userEvent.setup();
}

describe("composer", () => {
  beforeEach(() => localStorage.setItem("adobee-locale", "en"));

  it("sends the trimmed text on Enter and keeps Shift+Enter for a new line", async () => {
    const onSend = vi.fn();
    const user = setup({ onSend });
    const box = screen.getByRole("textbox", { name: en["agent.intent"] });
    await user.type(box, "  a quiet room{Shift>}{Enter}{/Shift}");
    expect(onSend).not.toHaveBeenCalled();
    await user.keyboard("{Enter}");
    expect(onSend).toHaveBeenCalledWith("a quiet room");
  });

  it("sends with the button, and not while empty", async () => {
    const onSend = vi.fn();
    const user = setup({ onSend });
    expect(screen.getByRole("button", { name: en["agent.send"] })).toBeDisabled();
    await user.type(screen.getByRole("textbox"), "hi");
    await user.click(screen.getByRole("button", { name: en["agent.send"] }));
    expect(onSend).toHaveBeenCalledWith("hi");
  });

  it("sends an example with one tap", async () => {
    const onSend = vi.fn();
    const user = setup({ onSend });
    expect(screen.getByText(en["agent.try"])).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: en["agent.example.3"] }));
    expect(onSend).toHaveBeenCalledWith(en["agent.example.3"]);
  });

  it("says it is busy and sends nothing more", async () => {
    const onSend = vi.fn();
    const user = setup({ onSend, busy: true, start: "hi" });
    expect(screen.getByRole("button", { name: en["agent.sending"] })).toBeDisabled();
    await user.click(screen.getByRole("textbox"));
    await user.keyboard("{Enter}");
    expect(onSend).not.toHaveBeenCalled();
  });
});

describe("composer box", () => {
  beforeEach(() => localStorage.setItem("adobee-locale", "de"));

  it("grows with its text, so a long request needs no inner scrollbar", () => {
    const spy = vi.spyOn(HTMLTextAreaElement.prototype, "scrollHeight", "get").mockReturnValue(210);
    setup({ onSend: vi.fn(), start: "lang" });
    const box = screen.getByRole("textbox");
    expect(box.style.height).toBe("210px");
    expect(box.style.overflowY).toBe("hidden");
    spy.mockRestore();
  });

  it("stops growing at about eight lines and scrolls from there", () => {
    const spy = vi.spyOn(HTMLTextAreaElement.prototype, "scrollHeight", "get").mockReturnValue(2000);
    setup({ onSend: vi.fn(), start: "lang" });
    const box = screen.getByRole("textbox");
    expect(parseInt(box.style.height)).toBeLessThan(400);
    expect(box.style.overflowY).toBe("auto");
    spy.mockRestore();
  });

  it("starts the search bar as one row", () => {
    const spy = vi.spyOn(HTMLTextAreaElement.prototype, "scrollHeight", "get").mockReturnValue(28);
    setup({ onSend: vi.fn(), start: "kurz", bar: true });
    const box = screen.getByRole("textbox");
    expect(box.style.height).toBe("28px");
    expect(box.style.overflowY).toBe("hidden");
    spy.mockRestore();
  });

  it("wraps a long search onto more rows, so the whole request stays readable", () => {
    const spy = vi.spyOn(HTMLTextAreaElement.prototype, "scrollHeight", "get").mockReturnValue(84);
    setup({ onSend: vi.fn(), start: "lang", bar: true });
    const box = screen.getByRole("textbox");
    expect(box.style.height).toBe("84px");
    expect(box.style.overflowY).toBe("hidden");
    expect(box.style.overflowX).not.toBe("auto");
    spy.mockRestore();
  });

  it("stops the search bar at five rows and scrolls from there", () => {
    const spy = vi.spyOn(HTMLTextAreaElement.prototype, "scrollHeight", "get").mockReturnValue(2000);
    setup({ onSend: vi.fn(), start: "lang", bar: true });
    const box = screen.getByRole("textbox");
    expect(box.style.height).toBe("140px");
    expect(box.style.overflowY).toBe("auto");
    spy.mockRestore();
  });
});
