// The public page shows the product only. Presenters open it with ?demo for their tools: the stress test, simulated
// traffic for the demand map, the tamper test and the raw MCP exchange.

/** True when the address carries ?demo. */
export const demoMode = (): boolean =>
  typeof window !== "undefined" && new URLSearchParams(window.location.search).has("demo");
