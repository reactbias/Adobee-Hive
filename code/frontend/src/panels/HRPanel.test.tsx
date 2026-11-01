import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "../i18n";
import en from "../i18n/en";
import HRPanel from "./HRPanel";

function show() {
  render(
    <I18nProvider>
      <HRPanel />
    </I18nProvider>,
  );
}

describe("the hiring panel", () => {
  afterEach(() => vi.unstubAllEnvs());

  it("says it is a script before it plays, and that nothing was sent after", async () => {
    show();
    expect(screen.getByText(en["hr.lead"])).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: en["hr.start"] }));
    expect(screen.getByText(en["hr.meta"])).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: en["chat.skip"] }));
    expect(await screen.findByText(en["hr.chat.summary"])).toBeInTheDocument();
  });

  it("never shows a yes the person did not give", async () => {
    show();
    fireEvent.click(screen.getByRole("button", { name: en["hr.start"] }));
    fireEvent.click(await screen.findByRole("button", { name: en["chat.skip"] }));
    await screen.findByText(en["hr.chat.summary"]);
    expect(screen.queryByText(en["trace.approved"])).toBeNull();
  });

  it("plays line by line, in words a person reads and with the right people talking", async () => {
    show();
    fireEvent.click(screen.getByRole("button", { name: en["hr.start"] }));
    // Playing, not jumped to the end: the summary is still to come and Skip is on offer.
    expect(screen.queryByText(en["hr.chat.summary"])).toBeNull();
    fireEvent.click(await screen.findByRole("button", { name: en["chat.skip"] }));
    await screen.findByText(en["hr.chat.summary"]);
    // The small tool tag above a line is the chat's own style; the line itself is for people.
    const lines = [...document.querySelectorAll(".msg p")].map((line) => line.textContent ?? "");
    expect(lines.filter((line) => /^(hr_|hub_)/.test(line))).toEqual([]);
    expect(screen.queryByText(en["chat.role.business"])).toBeNull();
    expect(screen.getAllByText(en["hr.speaker.candidate"]).length).toBeGreaterThan(0);
    expect(screen.getByText(en["hr.reply.connect"])).toBeInTheDocument();
  });

  it("gives the conversation the screen, and the form back on Change the job", async () => {
    show();
    fireEvent.click(screen.getByRole("button", { name: en["hr.start"] }));
    expect(screen.queryByLabelText(en["hr.job.title"])).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: en["hr.change"] }));
    fireEvent.change(screen.getByLabelText(en["hr.job.title"]), { target: { value: "Gardener" } });
    fireEvent.click(screen.getByRole("button", { name: en["hr.start"] }));
    expect(await screen.findByText(/^Gardener:/)).toBeInTheDocument();
  });

  it("offers the Hiring Hub only when this build knows where one is", async () => {
    vi.stubEnv("VITE_HIRING_HUB_URL", "");
    show();
    fireEvent.click(screen.getByRole("button", { name: en["hr.start"] }));
    fireEvent.click(await screen.findByRole("button", { name: en["chat.skip"] }));
    await screen.findByText(en["hr.chat.summary"]);
    expect(screen.queryByRole("link", { name: en["hr.handoff.open"] })).toBeNull();
  });

  it("links to the Hiring Hub's front door when it does", async () => {
    vi.stubEnv("VITE_HIRING_HUB_URL", "https://hiring.example/");
    show();
    fireEvent.click(screen.getByRole("button", { name: en["hr.start"] }));
    fireEvent.click(await screen.findByRole("button", { name: en["chat.skip"] }));
    const gate = (await screen.findByText(en["hr.handoff.title"])).closest(".gate") as HTMLElement;
    expect(within(gate).getByRole("link", { name: en["hr.handoff.open"] })).toHaveAttribute(
      "href",
      "https://hiring.example",
    );
  });
});
