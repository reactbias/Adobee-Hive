import { useEffect, useRef, useState } from "react";
import { api, apiOrigin, ApiError, HealthError, type Health } from "../api";
import { useI18n } from "../i18n";
import { moment } from "../lib/format";

type Check = {
  identity: string;
  phase: "checking" | "reachable" | "unreachable";
  health: Health | null;
  checkedAt: number | null;
  lastSuccessAt: number | null;
  error: unknown;
};

/** Backend reachability and configured planner mode are separate, refreshed only in a visible tab. */
export default function BackendStatus({
  hub = "",
  onHealth,
}: {
  hub?: string;
  onHealth?: (reached: boolean | undefined) => void;
}) {
  const { t, intl } = useI18n();
  const backend = apiOrigin();
  const identity = `${hub}@${backend}`;
  const [check, setCheck] = useState<Check | null>(null);
  const retry = useRef<(() => void) | null>(null);
  // A selection change must not show the previous backend's green state, even before effect cleanup runs.
  const current = check?.identity === identity ? check : null;
  const phase = current?.phase ?? "checking";
  const health = current?.health;

  useEffect(() => {
    let disposed = false;
    let pending: AbortController | null = null;
    let next: number | undefined;
    setCheck(null);
    onHealth?.(undefined);

    const isVisible = () => document.visibilityState !== "hidden";

    const refresh = async () => {
      if (disposed || pending || !isVisible()) return;
      clearTimeout(next);
      const request = new AbortController();
      pending = request;
      setCheck((previous) => ({
        identity,
        phase: "checking",
        health: null,
        checkedAt: previous?.checkedAt ?? null,
        lastSuccessAt: previous?.lastSuccessAt ?? null,
        error: null,
      }));
      try {
        const result = await api.health({ signal: request.signal });
        if (disposed || request.signal.aborted) return;
        const now = Date.now();
        setCheck({ identity, phase: "reachable", health: result, checkedAt: now, lastSuccessAt: now, error: null });
        onHealth?.(true);
      } catch (error) {
        if (disposed || request.signal.aborted) return;
        setCheck((previous) => ({
          identity,
          phase: "unreachable",
          health: null,
          checkedAt: Date.now(),
          lastSuccessAt: previous?.lastSuccessAt ?? null,
          error,
        }));
        onHealth?.(false);
      } finally {
        pending = null;
        if (!disposed && isVisible()) next = window.setTimeout(() => void refresh(), 15_000);
      }
    };
    const visibility = () => {
      clearTimeout(next);
      if (isVisible()) void refresh();
    };
    retry.current = () => void refresh();
    document.addEventListener("visibilitychange", visibility);
    void refresh();
    return () => {
      disposed = true;
      clearTimeout(next);
      pending?.abort();
      retry.current = null;
      document.removeEventListener("visibilitychange", visibility);
    };
  }, [identity, onHealth]);

  const live = health?.llm === "openai" || health?.llm === "claude";
  const failure =
    current?.error instanceof ApiError
      ? t("status.httpError", { status: current.error.status })
      : current?.error instanceof HealthError && current.error.kind === "timeout"
        ? t("status.timeoutError")
        : current?.error instanceof HealthError && current.error.kind === "response"
          ? t("status.responseError")
          : t("status.networkError");
  const checkedAt = current?.checkedAt != null ? new Date(current.checkedAt).toISOString() : null;
  const lastSuccessAt = current?.lastSuccessAt != null ? new Date(current.lastSuccessAt).toISOString() : null;

  return (
    <section className="backend-status" aria-label={t("status.title")}>
      <div className="backend-status-state" role="status">
        <span className={`status ${phase === "reachable" ? "ok" : phase === "unreachable" ? "no" : ""}`}>
          {t(phase === "reachable" ? "status.reachable" : phase === "unreachable" ? "nav.down" : "status.checking")}
        </span>
        <span
          className={`status ${live ? "ok" : health?.llm === "mock" ? "warm" : ""}`}
          title={live ? t("status.modelConfigured", { provider: health.llm, model: health.model }) : undefined}
        >
          {t(live ? "nav.live" : health?.llm === "mock" ? "nav.offline" : "status.modelUnknown")}
        </span>
      </div>
      <div className="backend-status-details">
        <span>{t("status.hub", { hub: hub || t("status.defaultHub") })}</span>
        <span className="backend-address">{backend}</span>
        {checkedAt && (
          <span>
            {t("status.lastChecked")} <time dateTime={checkedAt}>{moment(checkedAt, intl)}</time>
          </span>
        )}
        {phase !== "reachable" && lastSuccessAt && (
          <span>
            {t("status.lastSuccess")} <time dateTime={lastSuccessAt}>{moment(lastSuccessAt, intl)}</time>
          </span>
        )}
      </div>
      {phase === "unreachable" && (
        <div className="backend-status-failure">
          <span>{failure}</span>
          <button className="quiet" onClick={() => retry.current?.()}>
            {t("status.retry")}
          </button>
        </div>
      )}
    </section>
  );
}
