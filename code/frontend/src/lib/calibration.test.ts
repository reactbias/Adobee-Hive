import { describe, expect, it } from "vitest";
import { readCalibration, stars } from "./calibration";

// If this reads backwards on screen, the whole trust model reads backwards. So it is pinned here.
describe("calibration", () => {
  it("calls a positive error over-promising: the hub published more than people found", () => {
    expect(readCalibration(7, "weak")).toEqual({ reading: "over", stars: 0.7 });
  });

  it("calls a negative error underselling: the hub published less than people found", () => {
    expect(readCalibration(-12, "good")).toEqual({ reading: "under", stars: 1.2 });
  });

  it("calls zero exact", () => {
    expect(readCalibration(0, "good")).toEqual({ reading: "exact", stars: 0 });
  });

  it("keeps thin evidence unproven rather than showing it as zero or as bad", () => {
    expect(readCalibration(null, "unproven")).toEqual({ reading: "unproven", stars: 0 });
    expect(readCalibration(9, "unproven")).toEqual({ reading: "unproven", stars: 0 });
  });

  it("never reports a negative number of stars: the direction is the reading, not the sign", () => {
    for (const error of [-30, -1, 1, 30]) expect(readCalibration(error, "weak").stars).toBeGreaterThan(0);
  });

  it("writes tenths of a star as one decimal in the page's language", () => {
    expect(stars(0.4, "en-CH")).toBe("0.4");
    expect(stars(1, "de-CH")).toBe("1.0");
  });
});
