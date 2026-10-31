import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, HealthError, setChosenHub, type Health } from "../api";
import { I18nProvider } from "../i18n";
import en from "../i18n/en";
import BackendStatus from "./BackendStatus";

const offline: Health = {
  status: "ok",
  llm: "mock",
  model: "scripted",
  fast_model: "scripted",
  semantic: "offline",
};
const live: Health = { ...offline, llm: "openai", model: "live-model", fast_model: "fast-model" };
const flush = async () => act(async () => {});
const show = (hub = "basel") =>
  render(
    <I18nProvider>
      <BackendStatus hub={hub} />
    </I18nProvider>,
  );

beforeEach(() => {
  vi.restoreAllMocks();
  vi.useFakeTimers();
  vi.setSystemTime(new Date("2026-11-01T12:00:00Z"));
  vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible");
  localStorage.setItem("adobee-locale", "en");
  setChosenHub("");
});

afterEach(() => {
  vi.useRealTimers();
  setChosenHub("");
});

describe("backend and model status", () => {
  it("distinguishes a reachable offline planner from an unreachable backend", async () => {
    vi.spyOn(api, "health").mockResolvedValueOnce(offline).mockRejectedValue(new HealthError("network"));
    show();
    expect(screen.getByText(en["status.checking"])).toBeInTheDocument();
    expect(screen.getByText(en["status.modelUnknown"])).toBeInTheDocument();
    await flush();
    expect(screen.getByText(en["status.reachable"])).toBeInTheDocument();
    expect(screen.getByText(en["nav.offline"])).toBeInTheDocument();
    expect(screen.queryByText(en["nav.down"])).not.toBeInTheDocument();

    await act(async () => {
      vi.advanceTimersByTime(15_000);
    });
    expect(screen.getByText(en["nav.down"])).toBeInTheDocument();
    expect(screen.getByText(en["status.modelUnknown"])).toBeInTheDocument();
    expect(screen.queryByText(en["nav.offline"])).not.toBeInTheDocument();
    expect(screen.getByText(en["status.networkError"])).toBeInTheDocument();
  });

  it("removes stale green after a mid-session failure and retries immediately", async () => {
    const health = vi
      .spyOn(api, "health")
      .mockResolvedValueOnce(live)
      .mockRejectedValueOnce(new HealthError("timeout"));
    show();
    await flush();
    expect(screen.getByText(en["nav.live"])).toBeInTheDocument();

    await act(async () => {
      vi.advanceTimersByTime(15_000);
    });
    expect(screen.queryByText(en["nav.live"])).not.toBeInTheDocument();
    expect(screen.queryByText(en["status.reachable"])).not.toBeInTheDocument();
    expect(screen.getByText(en["status.timeoutError"])).toBeInTheDocument();
    expect(screen.getAllByRole("time")).toHaveLength(2);
    health.mockResolvedValueOnce(offline);
    fireEvent.click(screen.getByRole("button", { name: en["status.retry"] }));
    expect(screen.getByText(en["status.checking"])).toBeInTheDocument();
    await flush();
    expect(health).toHaveBeenCalledTimes(3);
    expect(screen.getByText(en["status.reachable"])).toBeInTheDocument();
    expect(screen.getByText(en["nav.offline"])).toBeInTheDocument();
  });

  it("keeps HTTP failures distinct from network and timeout failures", async () => {
    vi.spyOn(api, "health").mockRejectedValue(new ApiError("Unavailable", 503));
    show();
    await flush();
    expect(screen.getByText(en["status.httpError"].replace("{status}", "503"))).toBeInTheDocument();
    expect(screen.queryByText(en["status.networkError"])).not.toBeInTheDocument();
    expect(screen.getByText(en["status.modelUnknown"])).toBeInTheDocument();
  });

  it("aborts the previous hub's check and ignores its late success", async () => {
    let finishOld!: (health: Health) => void;
    const health = vi
      .spyOn(api, "health")
      .mockImplementationOnce(() => new Promise((resolve) => (finishOld = resolve)))
      .mockRejectedValueOnce(new HealthError("network"));
    const view = show();
    const oldSignal = health.mock.calls[0][0]?.signal;
    setChosenHub("zurich", "http://zurich.test:8000");
    view.rerender(
      <I18nProvider>
        <BackendStatus hub="zurich" />
      </I18nProvider>,
    );
    await flush();
    expect(oldSignal?.aborted).toBe(true);
    expect(screen.getByText("http://zurich.test:8000")).toBeInTheDocument();
    await act(async () => finishOld(live));
    expect(screen.getByText(en["nav.down"])).toBeInTheDocument();
    expect(screen.queryByText(en["nav.live"])).not.toBeInTheDocument();
    expect(screen.queryByText(en["status.reachable"])).not.toBeInTheDocument();
  });

  it("polls only while visible and refreshes as soon as the tab returns", async () => {
    const visibility = vi.spyOn(document, "visibilityState", "get");
    const health = vi.spyOn(api, "health").mockResolvedValue(offline);
    show();
    await flush();
    await act(async () => {
      vi.advanceTimersByTime(15_000);
    });
    expect(health).toHaveBeenCalledTimes(2);

    visibility.mockReturnValue("hidden");
    fireEvent(document, new Event("visibilitychange"));
    await act(async () => {
      vi.advanceTimersByTime(60_000);
    });
    expect(health).toHaveBeenCalledTimes(2);
    visibility.mockReturnValue("visible");
    fireEvent(document, new Event("visibilitychange"));
    await flush();
    expect(health).toHaveBeenCalledTimes(3);
  });

  it("does not schedule a check when the tab hides during an in-flight request", async () => {
    const visibility = vi.spyOn(document, "visibilityState", "get");
    let finish!: (health: Health) => void;
    const health = vi.spyOn(api, "health").mockImplementationOnce(() => new Promise((resolve) => (finish = resolve)));
    health.mockResolvedValue(offline);
    show();
    visibility.mockReturnValue("hidden");
    fireEvent(document, new Event("visibilitychange"));
    await act(async () => finish(offline));
    await act(async () => {
      vi.advanceTimersByTime(60_000);
    });
    expect(health).toHaveBeenCalledTimes(1);
    visibility.mockReturnValue("visible");
    fireEvent(document, new Event("visibilitychange"));
    await flush();
    expect(health).toHaveBeenCalledTimes(2);
    expect(screen.getByText(en["status.reachable"])).toBeInTheDocument();
  });

  it("waits until an initially hidden tab is visible and never overlaps checks", async () => {
    const visibility = vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
    let finish!: (health: Health) => void;
    const health = vi.spyOn(api, "health").mockImplementation(() => new Promise((resolve) => (finish = resolve)));
    show();
    await act(async () => {
      vi.advanceTimersByTime(30_000);
    });
    expect(health).not.toHaveBeenCalled();
    visibility.mockReturnValue("visible");
    fireEvent(document, new Event("visibilitychange"));
    fireEvent(document, new Event("visibilitychange"));
    await act(async () => {
      vi.advanceTimersByTime(30_000);
    });
    expect(health).toHaveBeenCalledTimes(1);
    await act(async () => finish(offline));
    await act(async () => {
      vi.advanceTimersByTime(15_000);
    });
    expect(health).toHaveBeenCalledTimes(2);
    expect(
      within(screen.getByRole("region", { name: en["status.title"] })).getByText(
        en["status.hub"].replace("{hub}", "basel"),
      ),
    ).toBeInTheDocument();
  });
});
