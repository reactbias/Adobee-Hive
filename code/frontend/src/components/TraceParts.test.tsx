import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Step } from "../api";
import { I18nProvider } from "../i18n";
import en from "../i18n/en";
import { Reply } from "./TraceParts";

// A discovery that failed must say so; "0 of 0 fit" would read as an empty directory.

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
