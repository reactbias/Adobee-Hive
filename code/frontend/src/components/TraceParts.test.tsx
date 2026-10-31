import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Step } from "../api";
import { I18nProvider } from "../i18n";
import en from "../i18n/en";
import { Reply } from "./TraceParts";

// A discovery that failed must say so; "0 of 0 fit" would read as an empty directory. And every result row says
// which hub it came from: a federated answer that hides its origin is the one thing this directory must not do.

const failed: Step = {
  tool: "hive_discover",
  input: { near: "basel sbb", guests: "two" },
  output: { matches: [], excluded: [], errors: [{ source: "Adobee Hive (Basel)", error: "guests: not an integer" }] },
};

describe("Reply", () => {
  it("shows a failed discovery as an error, not as zero results", () => {
    render(
      <I18nProvider>
        <Reply step={failed} />
      </I18nProvider>,
    );
    expect(screen.getByText(en["trace.reply.discoverFailed"])).toBeInTheDocument();
    expect(screen.queryByText(/0 of 0/)).not.toBeInTheDocument();
  });
});

const match = (over: Record<string, unknown> = {}) => ({
  id: "hotel-krafft",
  name: "Hotel Krafft",
  from_price_chf: 180,
  distance_m: 400,
  score: 0.8,
  why: [],
  ...over,
});
const found = (matches: Record<string, unknown>[], excluded: Record<string, unknown>[] = []): Step => ({
  tool: "hive_discover",
  input: {},
  output: { matches, excluded },
});

const show = (step: Step) =>
  render(
    <I18nProvider>
      <Reply step={step} />
    </I18nProvider>,
  );

describe("where a result came from", () => {
  it("says so even for a local result, so a missing label never means unknown", () => {
    show(found([match()]));
    expect(screen.getByText(en["result.fromThisHub"])).toBeInTheDocument();
  });

  it("names the hub and the distance for a result from a neighbour", () => {
    show(found([match({ hops: 1, provenance: { path: ["zurich", "basel"], hops: 1, origin: "zurich" } })]));
    expect(screen.getByText(/from zurich/)).toBeInTheDocument();
    expect(screen.getByText(/1 hops away/)).toBeInTheDocument();
  });

  it("names the origin and the relay, not just whoever handed the card over", () => {
    show(found([match({ hops: 2, provenance: { path: ["basel", "zurich", "us"], hops: 2, origin: "basel" } })]));
    expect(screen.getByText(/from basel/)).toBeInTheDocument();
    expect(screen.getByText(/relayed via zurich/)).toBeInTheDocument();
  });

  it("shows the whole route on demand", () => {
    show(found([match({ hops: 2, provenance: { path: ["basel", "zurich", "us"], hops: 2, origin: "basel" } })]));
    expect(screen.getByText(en["result.route"])).toBeInTheDocument();
    expect(screen.getByText("basel → zurich → us")).toBeInTheDocument();
  });

  it("says when the same card arrived by more than one route", () => {
    const route = { path: ["zurich", "us"], hops: 1, origin: "zurich", also_reached_by: [{}, {}] };
    show(found([match({ hops: 1, provenance: route })]));
    expect(screen.getByText(/also reached by 2 other routes/)).toBeInTheDocument();
  });

  it("names the hub of an excluded result too", () => {
    show(
      found(
        [],
        [
          match({
            id: "x",
            name: "Gare Central",
            why_not: ["no_dogs"],
            hops: 1,
            provenance: { path: ["zurich", "us"], hops: 1, origin: "zurich" },
          }),
        ],
      ),
    );
    expect(screen.getByText(/from zurich/)).toBeInTheDocument();
  });

  it("leaves the backend's order alone: distance is already in the score, and must not be applied twice", () => {
    const far = match({
      id: "far",
      name: "Far Hotel",
      hops: 2,
      provenance: { path: ["a", "b", "us"], hops: 2, origin: "a" },
    });
    show(found([far, match()]));
    const names = screen.getAllByText(/Hotel/).map((n) => n.textContent ?? "");
    expect(names[0]).toContain("Far Hotel");
  });
});
