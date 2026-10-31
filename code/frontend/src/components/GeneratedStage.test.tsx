import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { I18nProvider } from "../i18n";
import en from "../i18n/en";
import { sceneFor } from "../lib/cardView";
import GeneratedStage from "./GeneratedStage";

describe("generated card", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("draws the name, then the offerings, and the question only after one is chosen", () => {
    vi.useFakeTimers();
    const scene = sceneFor(en["agent.example.1"]);
    expect(scene).not.toBeNull();
    render(
      <I18nProvider>
        <GeneratedStage scene={scene!} onDetails={() => {}} />
      </I18nProvider>,
    );

    expect(screen.getByRole("heading", { name: "Hotel Krafft Basel" })).toBeInTheDocument();
    expect(screen.getByText("4.3 / 5")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Room reservation" })).not.toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(520);
    });
    expect(screen.getByRole("button", { name: /Room reservation/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Small event on the Rhine terrace/ })).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Room reservation with Hotel Krafft Basel?" }),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Room reservation/ }));
    expect(screen.queryByText("Free cancellation 48h. No prepayment.")).not.toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(520);
    });
    expect(screen.getByText("in-person")).toBeInTheDocument();
    expect(screen.queryByText("Free cancellation 48h. No prepayment.")).not.toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(520);
    });
    expect(screen.getByText("Free cancellation 48h. No prepayment.")).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Room reservation with Hotel Krafft Basel?" }),
    ).not.toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(520);
    });
    expect(screen.getByText("Quiet side rooms, dogs welcome")).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Room reservation with Hotel Krafft Basel?" }),
    ).not.toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(520);
    });
    expect(screen.getByRole("heading", { name: "Room reservation with Hotel Krafft Basel?" })).toBeInTheDocument();
  });

  it("draws the yes, then the rating, then the score the person gave", async () => {
    vi.useFakeTimers();
    const scene = sceneFor(en["agent.example.1"]);
    render(
      <I18nProvider>
        <GeneratedStage scene={scene!} onDetails={() => {}} />
      </I18nProvider>,
    );
    act(() => {
      vi.advanceTimersByTime(520);
    });
    fireEvent.click(screen.getByRole("button", { name: /Room reservation/ }));
    for (let i = 0; i < 6 && !screen.queryByRole("button", { name: en["card.yes"] }); i += 1) {
      act(() => {
        vi.advanceTimersByTime(520);
      });
    }

    fireEvent.click(screen.getByRole("button", { name: en["card.yes"] }));
    expect(screen.queryByText(en["card.yes.done"])).not.toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(520);
    });
    expect(screen.getByText(en["card.yes.done"])).toBeInTheDocument();
    expect(screen.queryByRole("radiogroup", { name: en["card.rate.ask"] })).not.toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(520);
    });
    fireEvent.click(screen.getByRole("radio", { name: "4" }));
    expect(screen.queryByText("4.0 / 5")).not.toBeInTheDocument();
    expect(screen.queryByText("0.0 / 5")).not.toBeInTheDocument();

    act(() => {
      vi.advanceTimersByTime(520);
    });
    expect(screen.getByText("4.0 / 5")).toBeInTheDocument();
    expect(screen.getByText(en["card.rate.yours"])).toBeInTheDocument();
  });
});
